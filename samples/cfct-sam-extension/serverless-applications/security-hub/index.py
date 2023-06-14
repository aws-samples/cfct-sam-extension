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

import boto3
import os
import cfnresponse


def lambda_handler(event, context):

    region = os.environ['AWS_REGION']
    account_id = context.invoked_function_arn.split(":")[4]
    sh = boto3.client('securityhub')

    # Change it to the desired standard to enable
    standardArn = f"arn:aws:securityhub:{region}::standards/pci-dss/v/3.2.1"

    # Change it to match the same standard, but adding account_id variable
    standardArnSubs = f"arn:aws:securityhub:{region}:{account_id}:subscription/pci-dss/v/3.2.1"

    standards_subscription_request = [{'StandardsArn': standardArn}]
    if (event['RequestType'] == 'Create' or event['RequestType'] == 'Update'):
        try:
            sh.batch_enable_standards(
                StandardsSubscriptionRequests=standards_subscription_request)
            print("Security Hub standard enabled")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        except Exception as ex:
            print("failed executing actions: " + str(ex))
            cfnresponse.send(event, context, cfnresponse.FAILED, {
                             "Exception": str(ex)})
    else:
        try:
            sh.batch_disable_standards(
                StandardsSubscriptionArns=[standardArnSubs])
            print("Security Hub with standard disabled")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        except Exception as ex:
            print("failed executing actions: " + str(ex))
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                             "Exception": str(ex)})
