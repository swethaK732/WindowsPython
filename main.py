import boto3
from datetime import datetime, timedelta, timezone
import smtplib
from smtplib import SMTPAuthenticationError, SMTPRecipientsRefused, SMTPException
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from botocore.exceptions import ClientError
import json
import os
import os
os.environ["AWS_REGION"] = "us-east-1"
aws_region = os.environ.get("AWS_REGION", "us-east-1")

# Create CloudWatch client
cloudwatch = boto3.client('cloudwatch')
lambda_client = boto3.client('lambda')

# # Time range: last 30 days
# END_TIME = datetime.now(timezone.utc)
# START_TIME = END_TIME - timedelta(days=30)
END_TIME = datetime.now(timezone.utc)
START_TIME = END_TIME - timedelta(minutes=5)

# --------------------------------
# SMTP Configuration
# --------------------------------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "ksswetha732@gmail.com"
# SMTP_PASSWORD =   # Use App Password
FROM_EMAIL = "noreply@gitkloud.com"
TO_EMAILS = ["swethashanmugampillai@gmail.com","bpantala@gitkloud.com"]

# -------------------------------
# AWS Secrets Manager to get SMTP password
# -------------------------------
secretname = os.environ.get("SECRET_NAME")

def get_secret(secret_string):

    secret_name = secretname
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    my_secret = json.loads(secret)[secret_string]
    return my_secret



def get_metric_sum(namespace, metric_name, dimensions):
    response = cloudwatch.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=START_TIME,
        EndTime=END_TIME,
        Period=300,  # 1 day
        Statistics=['Sum']
    )
    datapoints = response.get('Datapoints', [])
    return sum(dp.get('Sum', 0) for dp in datapoints) if datapoints else 0


# ------------------------
# Example 1: Lambda usage
# ------------------------
def check_unused_lambdas():
    unused = []
    paginator = lambda_client.get_paginator('list_functions')

    for page in paginator.paginate():
        for function in page['Functions']:
            invocations = get_metric_sum(
                'AWS/Lambda',
                'Invocations',
                [{'Name': 'FunctionName', 'Value': function['FunctionName']}]
            )
            if invocations == 0:
                unused.append(function['FunctionName'])
    return unused

# -------------------------------
# Send Email Notification
# -------------------------------
def send_email(unused_functions):
    try:
        SMTP_PASSWORD = get_secret("smtp_password")
        subject = f"Alert: Zero Invocations for Lambda functions"
        body = (
            f"I wanted to bring to your attention that over the last 5 minutes, "
            f"the following AWS Lambda functions in {aws_region} have recorded "
            f"zero invocations.\n\n"
            f"Monitoring Period: {START_TIME} to {END_TIME}\n"
            f"Actual Observation: No invocations registered.\n\n"
            f"Affected Lambda Functions:\n"
        )

        for fn in unused_functions:
            body += f"Function: {fn}\n"

        msg = MIMEMultipart()
        msg["From"] = FROM_EMAIL
        msg["To"] = ", ".join(TO_EMAILS)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        
        
            print("📧 Email sent successfully")
            return True

    except SMTPAuthenticationError:
        print("❌ SMTP Authentication failed: check SMTP username/password.")
        return False

    except SMTPRecipientsRefused as e:
        print(f"❌ Recipient addresses refused: {e.recipients}")
        return False

    except SMTPException as e:
        print(f"❌ SMTP error occurred: {e}")
        return False

    except Exception as e:
        print(f"❌ Unexpected error sending email: {e}")
        return False

if __name__ == "__main__":

    unused_lambdas = check_unused_lambdas()

    if unused_lambdas:
        result = send_email(unused_lambdas)
        print({
            "status": "sent" if result else "failed",
            "unused_count": len(unused_lambdas),
            "unused_functions": unused_lambdas,
        })
    else:
        print({"status": "no_unused_found", "unused_count": 0})
