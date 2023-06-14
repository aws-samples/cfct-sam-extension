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
import cfnresponse


def put_public_access_block(event, account_id):
    try:
        client = boto3.client('s3control')
        client.put_public_access_block(
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': True,
                'RestrictPublicBuckets': True
            },
            AccountId=account_id
        )

    except Exception as ex:
        msg = "Unable to configure S3 Bucket Public Access for the account {0}".format(
            account_id)
        print(msg)
        print("Failed executing actions: " + str(ex))
        raise Exception(str(ex))


def lambda_handler(event, context):

    account_id = context.invoked_function_arn.split(":")[4]

    if (event['RequestType'] == 'Create' or event['RequestType'] == 'Update'):
        try:
            put_public_access_block(event, account_id)
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        except Exception as ex:
            print("Failed executing actions: " + str(ex))
            cfnresponse.send(event, context, cfnresponse.FAILED, {
                             "Exception": str(ex)})
    elif event['RequestType'] == 'Delete':
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
    else:
        cfnresponse.send(event, context, cfnresponse.FAILED, {})
