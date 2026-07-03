import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("144.91.95.219", username="root", password="Pubagogo", timeout=15)

# 1. Profil actif + comptes Snap
_, out, _ = ssh.exec_command("python3 -c \"\nimport json\nfrom pathlib import Path\nbase=Path('/opt/storyscheduler/telegram_scraper')\nactive=json.load(open(base/'active_profile.json')).get('id','?')\nprofs=json.load(open(base/'profiles.json'))\nprof=next((p for p in profs if p['id']==active),{})\nprint('Profil actif:',active,'-',prof.get('name','?'))\nsnap=prof.get('snap_accounts',[])\nprint('Comptes Snap:',len(snap))\nfor a in snap: print(' ',a)\n\"")
print(out.read().decode('utf-8', errors='replace'))

# 2. Stories Snap en erreur/pending récentes
_, out2, _ = ssh.exec_command("python3 -c \"\nimport json\nfrom pathlib import Path\nbase=Path('/opt/storyscheduler/telegram_scraper')\nactive=json.load(open(base/'active_profile.json')).get('id','?')\nprofs=json.load(open(base/'profiles.json'))\nprof=next((p for p in profs if p['id']==active),{})\npdir=Path(prof.get('data_dir',str(base)))\npf=pdir/'profile_data'/active/'snap_scheduled.json'\nif not pf.exists(): pf=pdir/'snap_scheduled.json'\nif pf.exists():\n    d=json.load(open(pf))\n    recent=[s for s in d if s.get('status') in ('error','pending','posting')][-5:]\n    for s in recent: print(json.dumps(s,ensure_ascii=False)[:200])\nelse: print('Pas de snap_scheduled.json')\n\"")
print("=== Stories snap récentes ===")
print(out2.read().decode('utf-8', errors='replace'))

# 3. Logs Snap récents
_, out3, _ = ssh.exec_command("journalctl -u storyscheduler --since '1 hour ago' --no-pager 2>&1 | grep -i 'snap\\|oneup\\|cloudinary\\|error' | tail -20")
print("=== Logs snap ===")
print(out3.read().decode('utf-8', errors='replace'))
ssh.close()
