import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("144.91.95.219", username="root", password="Pubagogo", timeout=15)

# Écrire le script Python dans un fichier temporaire via SFTP
fix_script = '''import json

f = '/opt/storyscheduler/telegram_scraper/scheduled_stories.json'
stories = json.load(open(f))

fixed = 0
for s in stories:
    if s['status'] != 'partial':
        continue
    results = s.get('results', {})
    for acc_id, r in results.items():
        if r.get('status') == 'error' and 'premium' in r.get('error','').lower():
            results[acc_id] = {'status': 'pending'}
            fixed += 1
    statuses = [r['status'] for r in results.values()]
    if all(st == 'done' for st in statuses):
        s['status'] = 'done'
    elif all(st == 'error' for st in statuses):
        s['status'] = 'error'
    else:
        s['status'] = 'pending'

open(f,'w').write(json.dumps(stories, ensure_ascii=False, indent=2))
print(f"Fixed {fixed} entrees premium -> pending")
'''

sftp = ssh.open_sftp()
with sftp.file('/tmp/fix_premium.py', 'w') as f:
    f.write(fix_script)
sftp.close()

_, out, err = ssh.exec_command("python3 /tmp/fix_premium.py")
print(out.read().decode('utf-8', errors='replace'))
e = err.read().decode('utf-8', errors='replace')
if e: print("STDERR:", e)

_, out2, _ = ssh.exec_command("python3 -c \"import json; d=json.load(open('/opt/storyscheduler/telegram_scraper/scheduled_stories.json')); pend=[s for s in d if s['status']=='pending']; print(len(pend),'stories en attente de republication')\"")
print(out2.read().decode('utf-8', errors='replace'))

ssh.close()
