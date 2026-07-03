import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("144.91.95.219", username="root", password="Pubagogo", timeout=15)

# 1. Créer les dossiers sur le VPS
_, out, _ = ssh.exec_command(
    "mkdir -p /opt/storyscheduler/spotlight_pool /opt/storyscheduler/spotlight_posted && "
    "echo OK"
)
print("Dossiers:", out.read().decode().strip())

# 2. Mettre à jour spotlight_pool_dir dans le profil default
script = '''
import json
f = '/opt/storyscheduler/telegram_scraper/profiles.json'
profs = json.load(open(f))
changed = False
for p in profs:
    if p.get('id') == 'default' or p.get('name','').lower() == 'default' or len(profs)==1:
        old = p.get('spotlight_pool_dir','')
        p['spotlight_pool_dir'] = '/opt/storyscheduler/spotlight_pool'
        if 'spotlight_posted_dir' not in p or True:
            p['spotlight_posted_dir'] = '/opt/storyscheduler/spotlight_posted'
        print(f"Profile: {p.get('name', p.get('id','?'))}")
        print(f"  pool: {old} -> {p['spotlight_pool_dir']}")
        changed = True
        break
if changed:
    open(f,'w').write(json.dumps(profs, ensure_ascii=False, indent=2))
    print("Profil mis a jour")
else:
    print("Profil default introuvable")
'''
sftp = ssh.open_sftp()
with sftp.file('/tmp/fix_spotlight.py', 'w') as f:
    f.write(script)
sftp.close()
_, out2, err2 = ssh.exec_command("python3 /tmp/fix_spotlight.py")
print(out2.read().decode('utf-8', errors='replace'))
if err2.read().decode().strip():
    print("ERR:", err2.read().decode())

# 3. Redémarrer
_, out3, _ = ssh.exec_command("systemctl restart storyscheduler && sleep 2 && systemctl is-active storyscheduler")
print("Service:", out3.read().decode().strip())

ssh.close()
