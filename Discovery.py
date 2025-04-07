#!/usr/bin/env python3
import boto3
import botocore
import concurrent.futures
import json
import time
import sys
import argparse
from datetime import datetime

def validate_aws_credentials():
    """Validate that AWS credentials are configured and working"""
    try:
        print("Validating AWS credentials...")
        sts_client = boto3.client('sts')
        caller_identity = sts_client.get_caller_identity()
        print(f"AWS credentials valid. Authenticated as: {caller_identity['Arn']}")
        return True
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: AWS credentials not valid or insufficient permissions: {str(e)}")
        print("Please configure valid AWS credentials using one of the following methods:")
        print("  - AWS CLI: run 'aws configure'")
        print("  - Environment variables: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        print("  - Instance profile: if running on EC2")
        return False
    except botocore.exceptions.NoCredentialsError:
        print("ERROR: No AWS credentials found.")
        print("Please configure AWS credentials using one of the following methods:")
        print("  - AWS CLI: run 'aws configure'")
        print("  - Environment variables: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        print("  - Instance profile: if running on EC2")
        return False

def get_available_regions():
    """Get list of all available AWS regions"""
    try:
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        regions = [region['RegionName'] for region in ec2_client.describe_regions()['Regions']]
        return regions
    except Exception as e:
        print(f"Error getting AWS regions: {str(e)}")
        # Return default regions if we can't get the full list
        return ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2', 'eu-west-1']

def get_all_aws_services():
    """Get all available AWS services from boto3"""
    return sorted(boto3.Session().get_available_services())

def get_list_operations(client):
    """Find operations that might list resources for a service"""
    list_operations = []
    try:
        service_model = client._service_model
        for operation_name in service_model.operation_names:
            op_name = operation_name.lower()
            # Look for operations that likely list resources
            if (op_name.startswith('list') or 
                op_name.startswith('describe') or 
                (op_name.startswith('get') and ('list' in op_name or 'all' in op_name))):
                list_operations.append(operation_name)
    except Exception:
        pass
    return list_operations

def discover_resources_for_service(service_name, region):
    """Discover resources for a specific service using its API operations"""
    print(f"Scanning {service_name} in {region}...")
    resources = {}
    
    try:
        client = boto3.client(service_name, region_name=region)
        list_operations = get_list_operations(client)
        
        for operation in list_operations:
            try:
                # Skip operations known to cause issues or require complex parameters
                if operation in ['list_command_invocations', 'list_documents', 'list_resource_compliance_summaries', 
                               'list_tags_for_resource', 'list_buckets', 'list_multipart_uploads']:
                    continue
                    
                # Call the operation with no parameters
                response = getattr(client, operation)()
                
                # Extract just the relevant parts that likely contain resource lists
                filtered_response = {}
                for key, value in response.items():
                    if isinstance(value, list) and len(value) > 0:
                        filtered_response[key] = value
                    elif key.lower().endswith(('list', 'ids', 'arns', 'names', 'summaries')):
                        filtered_response[key] = value
                
                if filtered_response:
                    resources[operation] = filtered_response
                    print(f"  {service_name}.{operation} in {region}: Found {sum(len(v) if isinstance(v, list) else 1 for v in filtered_response.values())} resources")
                    
            except (botocore.exceptions.ClientError, 
                    botocore.exceptions.ParamValidationError, 
                    botocore.exceptions.OperationNotPageableError):
                # Skip operations that require parameters or have errors
                pass
            except Exception as e:
                # Log other unexpected errors but continue
                print(f"  Error with {service_name}.{operation} in {region}: {str(e)}")
    
    except Exception as e:
        print(f"Error initializing {service_name} in {region}: {str(e)}")
    
    return service_name, region, resources

def get_tagged_resources(region):
    """Get resources using AWS Resource Groups Tagging API (only returns tagged resources)"""
    print(f"Fetching tagged resources using Resource Groups Tagging API in {region}...")
    try:
        tagging_client = boto3.client('resourcegroupstaggingapi', region_name=region)
        resources = []
        
        paginator = tagging_client.get_paginator('get_resources')
        for page in paginator.paginate(ResourcesPerPage=100):
            resources.extend(page['ResourceTagMappingList'])
        
        # Group resources by service
        by_service = {}
        for resource in resources:
            arn = resource['ResourceARN']
            service = arn.split(':')[2]
            if service not in by_service:
                by_service[service] = []
            by_service[service].append(arn)
        
        print(f"Found {len(resources)} tagged resources across {len(by_service)} services in {region}")
        for service, arns in by_service.items():
            print(f"  {service} in {region}: {len(arns)} tagged resources")
            
        return resources
    except Exception as e:
        print(f"Error fetching tagged resources in {region}: {str(e)}")
        return []

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Discover AWS resources across your AWS account.")
    parser.add_argument("--regions", type=str, default="all",
                        help="Comma-separated list of regions to scan, or 'all' for all regions (default: all)")
    parser.add_argument("--services", type=str, default="all",
                        help="Comma-separated list of AWS services to scan, or 'all' for all services (default: all)")
    parser.add_argument("--threads", type=int, default=10,
                        help="Number of threads to use for concurrent scanning (default: 10)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename (default: aws_resources_<timestamp>.json)")
    return parser.parse_args()

def main():
    args = parse_arguments()
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Validate AWS credentials before proceeding
    if not validate_aws_credentials():
        sys.exit(1)  # Exit if credentials are not valid
    
    # Determine which regions to scan
    if args.regions.lower() == "all":
        regions = get_available_regions()
    else:
        regions = args.regions.split(',')
    
    # Determine which services to scan
    all_services = get_all_aws_services()
    if args.services.lower() == "all":
        services = all_services
    else:
        user_services = args.services.split(',')
        services = [s for s in user_services if s in all_services]
        if len(services) != len(user_services):
            print(f"Warning: Some specified services are not available in boto3.")
    
    # Set output filename
    output_file = args.output if args.output else f"aws_resources_{timestamp}.json"
    
    print(f"=== AWS RESOURCE DISCOVERY - {timestamp} ===")
    print(f"Scanning {len(regions)} regions: {', '.join(regions)}")
    print(f"Scanning {len(services)} services")
    print(f"Using {args.threads} threads for concurrent scanning")
    
    # Dictionary to store results for all regions
    all_results = {
        "metadata": {
            "timestamp": timestamp,
            "regions_scanned": regions,
            "services_scanned": services
        },
        "resources_by_region": {}
    }
    
    # Process each region
    for region in regions:
        print(f"\n=== Scanning region: {region} ===")
        
        # 1. Get tagged resources for this region
        tagged_resources = get_tagged_resources(region)
        
        # 2. Dynamically discover all resources across services for this region
        print(f"\nDiscovering resources using service-specific APIs in {region}...")
        
        # Use threading to speed up discovery
        region_resources = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
            future_to_service = {
                executor.submit(discover_resources_for_service, service, region): service 
                for service in services
            }
            
            for future in concurrent.futures.as_completed(future_to_service):
                service_name, region_name, service_resources = future.result()
                if service_resources:
                    region_resources[service_name] = service_resources
        
        # Store results for this region
        all_results["resources_by_region"][region] = {
            "tagged_resources": [resource["ResourceARN"] for resource in tagged_resources],
            "all_resources": region_resources
        }
    
    # Calculate totals across all regions
    total_tagged_resources = sum(
        len(all_results["resources_by_region"][region]["tagged_resources"]) 
        for region in regions
    )
    
    print(f"\n=== SUMMARY ===")
    print(f"Scanned {len(regions)} regions: {', '.join(regions)}")
    print(f"Found {total_tagged_resources} tagged resources across all regions")
    print(f"Scan completed in {time.time() - start_time:.2f} seconds")
    
    # Save results to file
    with open(output_file, "w") as f:
        json.dump(all_results, f, default=str, indent=2)
    
    print(f"Results saved to {output_file}")

if __name__ == "__main__":
    main()
