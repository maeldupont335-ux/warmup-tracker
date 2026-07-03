import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("144.91.95.219", username="root", password="Pubagogo", timeout=15)

# Retirer les comptes contaminés du profil principal (default)
# 6b8796dc appartient au profil 17c59ce3 (Louna), pas au profil principal
script = '''
import json
from pathlib import Path

# Profil principal = fichier racine
f = Path("/opt/storyscheduler/telegram_scraper/story_accounts.json")
accounts = json.load(open(f))

# IDs qui appartiennent VRAIMENT au profil principal (les 3 Pauline)
# Tous les autres sont de la contamination
PAULINE_IDS = {"e3e61319", "994d70d9", "5246a067"}
# Garder aussi 394a232a, f2e8182c, 9af27b24 si présents (comptes mystere du profil principal)

before = len(accounts)
clean = [a for a in accounts if a["id"] in PAULINE_IDS or
         Path(a.get("session_file","") + ".session").exists() and
         a["id"] not in {"6b8796dc","42f36780","175c0e65","3e57ca9a",
                         "6afbea25","af286749","b267c398","bb1f76fd",
                         "c28f6918","e35ab2b4"}]
open(f,"w").write(json.dumps(clean, ensure_ascii=False, indent=2))
print(f"Retiré {before-len(clean)} compte(s) contaminés. Reste: {len(clean)}")
for a in clean:
    print(f"  {a['id'][:8]} | {a.get('name','?')}")
'''
sftp = ssh.open_sftp()
with sftp.file('/tmp/fix_contamination.py', 'w') as f:
    f.write(script)
sftp.close()
_, out, err = ssh.exec_command("python3 /tmp/fix_contamination.py")
print(out.read().decode('utf-8', errors='replace'))
if err.read().decode().strip(): print("ERR:", err.read().decode())
_, out2, _ = ssh.exec_command("systemctl restart storyscheduler && sleep 2 && systemctl is-active storyscheduler")
print("Service:", out2.read().decode().strip())
ssh.close()
