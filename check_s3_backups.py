#!/usr/bin/env python3

##########################################################
#
# Written by David Kovar (Commity)
# david.kovar@commity.cz
# Based on the original work by Mathew McMillan:
# https://github.com/matt448/nagios-checks
#
#
# This Nagios check looks into a S3 bucket, list all folders in this bucket
# and checks the age and size of the latest file in each folder.
# Expected bucket structure is:
#   [mainbackup]   = Bucket
#     /service1
#       /backup-2020-01-01.tar.gz
#       /backup-2020-01-02.tar.gz
#       /backup-2020-01-03.tar.gz
#     /service2
#       /db-2020-01-01.sql.gz
#       /db-2020-01-02.sql.gz
#       /db-2020-01-03.sql.gz
#     /service3
#       /postgres-2020-01-01.dump
#       /postgres-2020-01-02.dump
#       /postgres-2020-01-03.dump
#
# For help on usage, run: ./check_s3_file_age.py --help
# Example usage: ./check_s3_file_age.py --bucketname mainbackup --bucketfolder service --minfirstage 240 --maxlastage 24 --checksize --aws-profile myprofile
#
#       In this case, the script will check the content of the "mainbackup" bucket, go through all folders matching
#       "service" name. In each folder (service1, service2, service3) it will check the age of the latest file
#       (it must not be older than 24 hours), and the age of the oldest file (it must not be newer than 240 hours).
#       Also, it will check the size of the latest file (it must not be smaller than 50% of the average folder's size).
#
# This script requires authentication credentials to be stored in
# one of the standard locations (see here: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html)
#
#
#
# -- Nagios error codes --
#    0 = OK/green
#    1 = WARNING/yellow
#    2 = CRITICAL/red
#    3 = UNKNOWN/purple
#

import datetime

import boto3
import botocore
from dateutil.tz import *
import argparse
import re


class Logger:
    debugEnabled = False

    def __init__(self, debug):
        self.debugEnabled = debug

    def debug(self, message):
        if self.debugEnabled:
            print("DEBUG: " + message)

    def info(self, message):
        print(message)


class S3Service:
    def __init__(self, profile, logger = Logger(False)):
        self.profile = profile
        self.session = boto3.Session(profile_name=self.profile)
        self.s3 = self.session.client("s3")
        self.logger = logger

    # Check if the bucket exists. Returns True if it does, False if it doesn't.
    def checkBucketExists(self, bucketName):
        try:
            self.s3.head_bucket(Bucket=bucketName)
            return True
        except botocore.exceptions.ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            if error_code == 404:
                self.logger.info(f"CRITICAL: No bucket found with a name of {str(bucketName)}")
            else:
                self.logger.info(f"CRITICAL: Error code: {e.response['Error']}")

            return False

    def listFolders(self, bucketName):
        try:
            foldersObject = self.s3.list_objects_v2(Bucket=bucketName, Delimiter="/")["CommonPrefixes"]
            return list(map(lambda x: x["Prefix"].rstrip("/"), foldersObject))
        except Exception as e:
            self.logger.info("CRITICAL: No folder found in bucket " + str(bucketName))
            self.logger.debug(str(e))
            exit(2)

    def listFiles(self, bucketName, folderName):
        try:
            return self.s3.list_objects_v2(Bucket=bucketName, Prefix=folderName)["Contents"]
        except Exception as e:
            self.logger.info("CRITICAL: No file found in folder " + str(folderName))
            self.logger.debug(str(e))
            exit(2)


# Parse command line arguments
parser = argparse.ArgumentParser(description="This script is a Nagios check that \
                                              monitors the age of files that have \
                                              been backed up to an S3 bucket.")

parser.add_argument("--bucketname", dest="bucketname", type=str, required=True,
                    help="Name of S3 bucket")

parser.add_argument("--bucketfolder", dest="bucketfolder", type=str, default="",
                    help="Folder to check inside bucket (optional).")

parser.add_argument("--minfirstage", dest="minfirstage", type=int, default=0,
                    help="Minimum age for the oldest backup in an S3 bucket in hours. \
                          Default is 0 hours (disabled).")

parser.add_argument("--maxlastage", dest="maxlastage", type=int, default=0,
                    help="Maximum age for youngest backup in an S3 bucket in hours. \
                          Default is 0 hours (disabled).")

parser.add_argument("--checksize", action="store_true",
                    help="Check the size of the last backup in the bucket. Default is 1 (enabled).")

parser.add_argument("--aws-profile", dest="profile", type=str, default="default",
                    help="AWS profile name from ~/.aws/credentials file. Default is 'default'.")

parser.add_argument("--listfiles", action="store_true",
                    help="Enables listing of all latest backups in bucket to stdout. \
                          Use with caution!")

parser.add_argument("--debug", action="store_true",
                    help="Enables debug output.")

args = parser.parse_args()

# Assign variables from command line arguments
logger = Logger(args.debug)
bucketname = args.bucketname
minfirstage = args.minfirstage
maxlastage = args.maxlastage
bucketfolder = args.bucketfolder
bucketfolder_regex = "^" + bucketfolder
maxagetime = datetime.datetime.now(tzutc()) - datetime.timedelta(hours=maxlastage)
minagetime = datetime.datetime.now(tzutc()) - datetime.timedelta(hours=minfirstage)

maxfilecount = 0
minfilecount = 0
totalfilecount = 0
sizeWarningCount = 0
sizeErrorCount = 0

logger.debug("########## START DEBUG OUTPUT ############")
logger.debug("S3 BUCKET NAME: " + str(bucketname))
logger.debug("MIN FILE AGE: " + str(minfirstage))
logger.debug("MAX FILE AGE: " + str(maxlastage))
logger.debug("S3 profile name: " + str(args.profile))
logger.debug("MAX AGE TIME: " + str(maxagetime))
logger.debug("MIN AGE TIME: " + str(minagetime))

logger.debug("Connecting to S3")

s3Service = S3Service(args.profile, logger)

# Check if the bucket exists
s3Service.checkBucketExists(bucketname)
logger.debug(f"Hooray the bucket {str(bucketname)} was found!")

folders = s3Service.listFolders(bucketname)
logger.debug(f"Folders: {folders}")

# Loop through folders in the S3 bucket and for each of them get the oldest file.
# For each of them, check age and size.
for folder in folders:
    if re.match(bucketfolder_regex, str(folder)):
        files = s3Service.listFiles(bucketname, folder)
        sortedFiles = sorted(files, key=lambda x: x["LastModified"], reverse=True)
        youngestFile = sortedFiles[0]
        oldestFile = sortedFiles[-1]
        if args.listfiles:
            logger.info(f"{youngestFile['Key']}|{youngestFile['StorageClass']}|{str(youngestFile['LastModified'])}|{youngestFile['Size']}")

        if youngestFile["LastModified"] < maxagetime:
            if args.listfiles:
                logger.info(f"Found backup older than maxlastage of {str(maxlastage)} hours: {youngestFile['Key']}")
            maxfilecount += 1

        if minfirstage > 0 and oldestFile["LastModified"] > minagetime:
            if args.listfiles:
                logger.info(f"Found file newer than minfirstage of {str(minfirstage)} hours: {oldestFile['Key']}")
            minfilecount += 1
        totalfilecount += 1

        if args.checksize:
            totalSize = sum(map(lambda x: x["Size"], files))
            averageSize = totalSize / len(files)
            if youngestFile["Size"] < averageSize / 2:
                logger.info(f"File size of {youngestFile['Key']} is less than 50% of average size")
                sizeWarningCount += 1

            if youngestFile["Size"] == 0:
                logger.info(f"CRITICAL: File size of {youngestFile['Key']} is 0")
                sizeErrorCount += 1

# Begin formatting the status message for Nagios output
# This is conditionally formatted based on requested min/max options.
msg = " -"
if minfirstage > 0:
    msg += f" MIN:{str(minfirstage)}hrs"
if maxlastage > 0:
    msg += f" MAX:{str(maxlastage)}hrs"

if maxlastage > 0:
    msg += " - Files exceeding MAX time: " + str(maxfilecount)

if minfirstage > 0:
    msg += " - Files before MIN time: " + str(minfilecount)

if sizeWarningCount > 0:
    msg += " - File with SIZE warning: " + str(sizeWarningCount)

if sizeErrorCount > 0:
    msg += " - File with SIZE error: " + str(sizeErrorCount)

msg += " - Total file count: " + str(totalfilecount)

# Decide exit code for Nagios based on maxfilecount, minfilecount, sizeWarning and sizeError results.
#
if minfirstage == 0 and maxlastage == 0:
    statusline = "WARNING: No max or min specified. Please specify at least one." + msg
    exitcode = 1
elif maxlastage > 0 and maxfilecount > 0:
    statusline = "CRITICAL: One of S3 backups exceed MAX time boundaries." + msg
    exitcode = 2
elif minfirstage > 0 and minfilecount > 0:
    statusline = "CRITICAL: One of S3 backups exceed MIN time boundaries." + msg
    exitcode = 2
elif sizeErrorCount > 0:
    statusline = "CRITICAL: One of S3 backups has 0 size." + msg
    exitcode = 2
elif sizeWarningCount > 0:
    statusline = "WARNING: One of S3 backups has suspiciously small size." + msg
    exitcode = 1
elif maxfilecount == 0 and minfilecount == 0 and sizeErrorCount == 0 and sizeWarningCount == 0:
    statusline = "OK: S3 backups are OK." + msg
    exitcode = 0
else:
    statusline = "UNKNOWN: " + msg
    exitcode = 3

logger.info(statusline)
exit(exitcode)
