# Copyright 2023 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.


# This file is to easily test the CodeBuild steps.
# It's content is copied and deployed inside /source/cfct-sam-extension.yml --> CodeBuilProject

# Execution:
# EnabledRegions=REGION1,REGION2 DestinationBucketWithoutRegion=BUCKETNAME EnableContinuousDeployment=No python codebuild-local-test.py

import os
from subprocess import check_output
import boto3
import logging
import json
import io
from botocore.exceptions import ClientError

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

s3  = boto3.client('s3')
ssm = boto3.client('ssm')

enabled_regions       = os.environ["EnabledRegions"]
destination_bucket    = os.environ["DestinationBucketWithoutRegion"]
continous_deployment  = os.environ["EnableContinuousDeployment"]


def deploy_serverless_apis():
    """
    This function uploads api.json files to S3 only. No specific AWS SAM call/transformation needed.

    The uploaded file can be consumed by CfCT via AWS::Serverless::Api.DocumentUri.
    """
    logger.info("Execute serverless-apis")

    root_dir = "serverless-apis"
    dirs     = get_dirs_to_execute(root_dir)

    if not dirs:
        return

    for dir_name in dirs:
        runtime_config = None
        file_path = f"{root_dir}/{dir_name}/api.json"

        try:
            with open(file_path) as f:
                # Check if valid JSON is included.
                json.load(f)
        except FileNotFoundError as e:
            logger.error("serverless-api(s) need an api.json file to package for S3 upload.")
            logger.error(e)
            raise e

        for enabled_region in enabled_regions.split(","):
            bucket_name = f"{destination_bucket}-{enabled_region}"

            s3.upload_file(file_path, bucket_name, file_path)

        # Create or Update SSM Parameter
        try:
            logger.debug(f"ssm-value-to-store: /cfct-sam-extension/{root_dir}/{dir_name}={file_path}")
            ssm.put_parameter(Name=f"/cfct-sam-extension/{root_dir}/{dir_name}", Value=file_path,
                              Type='String', Overwrite=True, Tier='Standard')
        except ClientError as e:
            logger.error(e)


def deploy_serverless_applications():
    """
    Builds and packages a full CFN stack.

    Output can be consumed by CfCT via AWS::CloudFormation::Stack.TemplateURL
    (Due to a bug in Serverless::Application's reference, the default CFN resource needs to be used. See cfct examples for more details.)
    """
    logger.info("Execute serverless-applications")

    root_dir = "serverless-applications"
    dirs = get_dirs_to_execute(root_dir)

    if not dirs:
        return

    for dir_name in dirs:

        execute_sam_build(root_dir, dir_name)

        template_name = f"{root_dir}/{dir_name}/template.yml"

        for enabled_region in enabled_regions.split(","):
            bucket_name = f"{destination_bucket}-{enabled_region}"

            # Package SAM source code to the destination bucket
            cmd_package = f"cd ./{root_dir}/{dir_name} && \
                            sam package \
                            --s3-bucket {bucket_name} \
                            --s3-prefix {root_dir}/{dir_name} \
                            --force-upload"
            logger.debug(cmd_package)

            template = check_output([cmd_package], shell=True)
            fileobject = io.BytesIO(template)
            s3.upload_fileobj(fileobject, bucket_name, template_name)

            logger.debug(f"file uploaded: {template_name}")

        # Create or Update SSM Parameter
        try:
            logger.debug(f"ssm-value-to-store: /cfct-sam-extension/{root_dir}/{dir_name}={template_name}")
            ssm.put_parameter(Name=f"/cfct-sam-extension/{root_dir}/{dir_name}", Value=template_name,
                              Type='String', Overwrite=True, Tier='Standard')
        except ClientError as e:
            logger.error(e)


def deploy_serverless_functions():
    """
    AWS::Serverless::Function
    Builds and packages functions. It requires a config.json file with a runtime property to build via sam build.

    Output can be consumed by CfCT via AWS::Serverless::Function.CodeUri
    """
    logger.info("Execute serverless-functions")

    root_dir = "serverless-functions"
    dirs     = get_dirs_to_execute(root_dir)

    if not dirs:
        return

    for dir_name in dirs:
        runtime_config = None

        try:
            with open(f"./{root_dir}/{dir_name}/config.json") as f:
                runtime_config = json.load(f)
        except FileNotFoundError as e:
            logger.error("serverless-function(s) need a config.json file to provide runtime to build with.")
            logger.error(e)
            raise e

        cfn_template = {
          "AWSTemplateFormatVersion": "2010-09-09",
          "Transform": "AWS::Serverless-2016-10-31",
          "Resources": {
            "LambdaFunction": {
              "Type": "AWS::Serverless::Function",
              "Properties": {
                "CodeUri": ".",
                "Runtime": runtime_config["runtime"],
                "Handler": "irrelevant"
              }
            }
          }
        }

        with open(f"./{root_dir}/{dir_name}/template.json", "w") as template_file:
            json.dump(cfn_template, template_file, indent=4)

        execute_sam_build(root_dir, dir_name)

        for enabled_region in enabled_regions.split(","):
            bucket_name = f"{destination_bucket}-{enabled_region}"

            # Package SAM source code to the destination bucket
            cmd_package = f"cd ./{root_dir}/{dir_name} && \
                            sam package \
                            --s3-bucket {bucket_name} \
                            --s3-prefix {root_dir}/{dir_name} \
                            --force-upload \
                            --use-json \
                            | jq '.Resources.LambdaFunction.Properties.CodeUri' \
                            | jq 'match(\"(s3://.*?/)(.*)\").captures[1].string'"
            logger.debug(cmd_package)

            zip_file_path = check_output([cmd_package], shell=True)
            logger.debug(f"zip_file_path={zip_file_path}")
            zip_file_path_formatted = zip_file_path.lstrip(b"b'\"").rstrip().rstrip(b"\"")

        # Create or Update SSM Parameter
        try:
            logger.debug(f"ssm-value-to-store: /cfct-sam-extension/{root_dir}/{dir_name}={zip_file_path_formatted.decode()}")
            ssm.put_parameter(Name=f"/cfct-sam-extension/{root_dir}/{dir_name}", Value=zip_file_path_formatted.decode(),
                              Type='String', Overwrite=True, Tier='Standard')
        except ClientError as e:
            logger.error(e)


def deploy_serverless_httpapis():
    """
    This function uploads api.json files to S3 only. No specific AWS SAM call/transformation needed.

    The uploaded file can be consumed by CfCT via AWS::Serverless::HttpApi.DocumentUri.
    """
    logger.info("Execute serverless-httpapis")

    root_dir = "serverless-httpapis"
    dirs     = get_dirs_to_execute(root_dir)

    if not dirs:
        return

    for dir_name in dirs:
        runtime_config = None
        file_path = f"{root_dir}/{dir_name}/api.json"

        try:
            with open(file_path) as f:
                # Check if valid JSON is included.
                json.load(f)
        except FileNotFoundError as e:
            logger.error("serverless-httpapi(s) need an api.json file to package for S3 upload.")
            logger.error(e)
            raise e

        for enabled_region in enabled_regions.split(","):
            bucket_name = f"{destination_bucket}-{enabled_region}"

            s3.upload_file(file_path, bucket_name, file_path)

        # Create or Update SSM Parameter
        try:
            logger.debug(f"ssm-value-to-store: /cfct-sam-extension/{root_dir}/{dir_name}={file_path}")
            ssm.put_parameter(Name=f"/cfct-sam-extension/{root_dir}/{dir_name}", Value=file_path,
                              Type='String', Overwrite=True, Tier='Standard')
        except ClientError as e:
            logger.error(e)


def deploy_serverless_state_machines():
    """
    This function uploads state-machine.json files to S3 only. No specific AWS SAM call/transformation needed.

    The uploaded file can be consumed by CfCT via AWS::Serverless::StateMachine.DefinitionUri.
    """
    logger.info("Execute serverless-state-machines")

    root_dir = "serverless-state-machines"
    dirs     = get_dirs_to_execute(root_dir)

    if not dirs:
        return

    for dir_name in dirs:
        runtime_config = None
        file_path = f"{root_dir}/{dir_name}/state-machine.json"

        try:
            with open(file_path) as f:
                # Check if valid JSON is included.
                json.load(f)
        except FileNotFoundError as e:
            logger.error("serverless-state-machine(s) need an api.json file to package for S3 upload.")
            logger.error(e)
            raise e

        for enabled_region in enabled_regions.split(","):
            bucket_name = f"{destination_bucket}-{enabled_region}"

            s3.upload_file(file_path, bucket_name, file_path)

        # Create or Update SSM Parameter
        try:
            logger.debug(f"ssm-value-to-store: /cfct-sam-extension/{root_dir}/{dir_name}={file_path}")
            ssm.put_parameter(Name=f"/cfct-sam-extension/{root_dir}/{dir_name}", Value=file_path,
                              Type='String', Overwrite=True, Tier='Standard')
        except ClientError as e:
            logger.error(e)


def get_dirs_to_execute(root_dir):
    if not os.path.isdir(f"./{root_dir}"):
        return

    dirs = [dir for dir in os.listdir(f"./{root_dir}/") if os.path.isdir(f"./{root_dir}/{dir}")]
    logger.debug(dirs)

    return dirs


def execute_sam_build(root_dir, dir_name) -> str:
    cmd_build = f"cd ./{root_dir}/{dir_name} && sam build"
    logger.debug(cmd_build)

    return check_output([cmd_build], shell=True)


deploy_serverless_apis()
deploy_serverless_applications()
deploy_serverless_functions()
deploy_serverless_httpapis()
deploy_serverless_state_machines()

if continous_deployment == "Yes":
    codepipeline = boto3.client('codepipeline')
    codepipeline.start_pipeline_execution(name='Custom-Control-Tower-CodePipeline')