nagios-checks
=============

A bunch of Nagios (Icinga) checks, that may be useful to other people.

Documentation for each script is in the header of the script itself.

## Installation
1. Copy the scripts to your Nagios plugins directory (e.g. `/usr/lib/nagios/plugins`) and make them executable
2. Add the checks to your Nagios configuration file `commands.conf`:
   ````
   object CheckCommand "check-s3-backups" {
     command = [ PluginDir + "/check_s3_backups.py" ]
     
     arguments = {
       "--bucketname" = {
         required = true
         skip_key = true
         value = "$check_s3_backups_bucket$"
         order = 100
       }
       "--bucketfolder" = {
         required = false
         value = "$check_s3_backups_folder$"
       }
       "--minfirstage" = {
         required = false
         value = "$check_s3_backup_minfirstage$"
         description = "Critical if the FIRST BACKUP is younger than AGE hours."
       }
       "--maxlastage" = {
         required = false
         value = "$check_s3_backup_maxlastage$"
         description = "Critical if the LAST BACKUP is older than AGE hours."
       }
       "--checksize" = {
         required = false
         set_if = "$check_s3_backup_checksize$"
         description = "Check the size of the LAST BACKUP files."
       }
       "--aws-profile" = {
         required = false
         value = "$check_s3_backup_profile$"
         description = "AWS profile name from ~/.aws/credentials file. Default is 'default'."
       }
     }
    
     vars.file_exists_glob_invert = false
     vars.file_exists_glob_alert_dir = false
   }
   ```
3. Add the checks to your Nagios configuration file `services.conf`:
   ````
    apply Service "s3-backups" {
      import "generic-service"
      check_command = "check-s3-backups"
      vars.check_s3_backups_bucket = "my-bucket"
      vars.check_s3_backup_maxlastage = "48"
      vars.check_s3_backup_checksize = "true"
      assign where host.vars.os == "Linux"
    }
   ````   
4. Restart Nagios

## Requirement
- Python 3.6 or later
- python packages: dateutil, boto3

## Credits
Originated from https://github.com/matt448/nagios-checks