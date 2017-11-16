#!/usr/bin/env python
'''
    This is the main entry point for the bot. All modules will be loaded from here. There are a number of environment
    variables that are required for this bot to function.
    See the README at https://github.com/meraki/spark-operations-bot
'''
import os
from ciscosparkbot import SparkBot
import cico_meraki
import cico_spark_call
import cico_combined
import cico_common
import cico_umbrella
import sys
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import umbrella_log_collector
import meraki_dashboard_link_parser

# ========================================================
# Load required parameters from environment variables
# ========================================================

# If there is a PORT environment variable, use that to map the Flask port. Used for Heroku.
# If no port set, use default of 5000.
app_port = os.getenv("PORT")
if not app_port:
    app_port = 5000
else:
    app_port = int(app_port)

# Load additional environment variables
bot_email = os.getenv("SPARK_BOT_EMAIL")
spark_token = os.getenv("SPARK_BOT_TOKEN")
bot_url = os.getenv("SPARK_BOT_URL")
bot_app_name = os.getenv("SPARK_BOT_APP_NAME")

# If any of the bot environment variables are missing, terminate the application
if not bot_email or not spark_token or not bot_url or not bot_app_name:
    print("app.py - Missing Environment Variable.")
    sys.exit()


# ========================================================
# Initialize Program - Run any pre-flight actions required
# ========================================================

# This function is called by the scheduler to download logs from Amazon S3 (for Umbrella)
def job_function():
    umbrella_log_collector.get_logs()


# Monkey patch send_help in SparkBot to allow removing built-in commands
def my_remove_command(self, command):
    """
    Remove a command from the bot
    :param command: The command string, example "/status"
    :return:
    """
    del self.commands[command]


SparkBot.remove_command = my_remove_command
# Monkey patch done.


# Check to see if a dashboard username and password has been provided. If so, scrape the dashboard to build
# cross-launch resources to use for the bot, otherwise initialize to None
if cico_common.meraki_dashboard_support():
    print("Attempting to resolve Dashboard references...")
    dbmap = meraki_dashboard_link_parser.get_meraki_http_info()
    cico_meraki.meraki_dashboard_map = dbmap
    print("Dbmap=", dbmap)
else:
    cico_meraki.meraki_dashboard_map = None


# If the Umbrella environment variables (aka Amazon S3) have been configured, enable the job scheduler to run every
# 5 minutes to download logs.
if cico_common.umbrella_support():
    cron = BackgroundScheduler()

    # Explicitly kick off the background thread
    cron.start()
    job = cron.add_job(job_function, 'interval', minutes=5)
    print("Beginning Umbrella Log Collection...")
    job_function()

    # Shutdown your cron thread if the web process is stopped
    atexit.register(lambda: cron.shutdown(wait=False))

# ========================================================
# Initialize Bot - Register commands and start web server
# ========================================================

# Create a new bot
bot = SparkBot(bot_app_name, spark_bot_token=spark_token,
               spark_bot_url=bot_url, spark_bot_email=bot_email, debug=True)

bot.add_command('help', 'Get help.', bot.send_help)
bot.remove_command('/echo')
bot.remove_command('/help')

# Add bot commands.
# If Meraki environment variables have been enabled, add Meraki-specifc commands.
if cico_common.meraki_support():
    bot.add_command('meraki-health', 'Get health of Meraki environment.', cico_meraki.get_meraki_health_html)
    bot.add_command('meraki-check', 'Check Meraki user status.', cico_meraki.get_meraki_clients_html)
# If Spark Call environment variables have been enabled, add Spark Call-specifc commands.
if cico_common.spark_call_support():
    bot.add_command('spark-health', 'Get health of Spark environment.', cico_spark_call.get_spark_call_health_html)
    bot.add_command('spark-check', 'Check Spark user status.', cico_spark_call.get_spark_call_clients_html)
# If Umbrella (S3) environment variables have been enabled, add Umbrella-specifc commands.
if cico_common.umbrella_support():
    bot.add_command('umbrella-health', 'Get health of Umbrella envrionment.', cico_umbrella.get_umbrella_health_html)
    bot.add_command('umbrella-check', 'Check Umbrella user status.', cico_umbrella.get_umbrella_clients_html)
# Add generic commands.
bot.add_command('health', 'Get health of entire environment.', cico_combined.get_health)
bot.add_command('check', 'Get user status.', cico_combined.get_clients)


# Run Bot
bot.run(host='0.0.0.0', port=app_port)