import paramiko, sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("144.91.95.219", username="root", password="Pubagogo", timeout=15)

sftp = ssh.open_sftp()
sftp.put(
    r"C:\Users\MAEL\Downloads\higgsfield-batch\higgsfield-batch\telegram_scraper\story_scheduler.py",
    "/opt/storyscheduler/telegram_scraper/story_scheduler.py"
)
sftp.close()
print("Upload OK")

stdin, stdout, stderr = ssh.exec_command("systemctl restart storyscheduler && sleep 2 && systemctl is-active storyscheduler")
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
print("Service:", out)
if err: print("STDERR:", err)
ssh.close()
