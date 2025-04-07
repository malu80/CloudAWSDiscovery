**AWS Resource Discovery Tool**
A comprehensive Python tool to dynamically discover and inventory all resources across AWS accounts and regions. This tool uses AWS API calls to detect both tagged and untagged resources, providing a complete view of your AWS infrastructure.

Features
Complete Resource Discovery: Identifies both tagged and untagged resources
Multi-Region Support: Can scan all AWS regions or specific regions
Dynamic Service Detection: Automatically works with all available AWS services
Credential Validation: Validates AWS credentials before scanning
Configurable: Customize regions, services, and concurrency
Detailed Output: Comprehensive JSON output for further processing
Performance Optimized: Uses concurrent processing for faster scanning
Prerequisites
Python 3.6 or higher
AWS credentials with read access to resources
boto3 Python package
Installation
Clone or download this repository
Install required dependencies:
Ensure your AWS credentials are configured using one of these methods:
AWS CLI: aws configure
Environment variables: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
Instance profile (if running on EC2)
Usage
Basic Usage
This will scan all regions and services using default settings.

Specific Regions
Specific Services
Custom Output File
Adjust Concurrency
Command-Line Arguments
Argument	Description	Default
--regions	Comma-separated list of regions to scan	all (all regions)
--services	Comma-separated list of AWS services to scan	all (all services)
--threads	Number of threads for concurrent scanning	10
--output	Output filename	aws_resources_<timestamp>.json
Output Format
The tool generates a JSON file with the following structure:

Security Considerations
This tool requires read-only permissions to AWS services
The output file contains detailed information about your AWS resources
Consider securing the output file as it may contain sensitive information
For large environments, be aware of AWS API rate limits
Limitations
Some AWS API operations require specific parameters and may be skipped
Global services like IAM, Route53, and CloudFront are only queried once
Very large AWS environments may experience API throttling
The tool cannot discover resources it doesn't have permissions to access
License
This project is licensed under the MIT License - see the LICENSE file for details.
