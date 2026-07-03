import paramiko, json
from datetime import datetime

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("144.91.95.219", username="root", password="Pubagogo", timeout=15)

stdin2,stdout2,_ = ssh.exec_command("cat /opt/storyscheduler/telegram_scraper/profile_data/17c59ce3/snap_scheduled.json")
j = json.loads(stdout2.read().decode())

pending = sorted([e for e in j if e.get("status") == "pending"], key=lambda x: x.get("scheduled_at",""))
done    = [e for e in j if e.get("status") == "done"]
error   = [e for e in j if e.get("status") == "error"]

print("=== LOUNA — Snapchat scheduled ===")
print("TOTAL  : " + str(len(j)))
print("pending: " + str(len(pending)) + "  (en file locale, seront envoyés à OneUp au moment H)")
print("done   : " + str(len(done)))
print("erreur : " + str(len(error)))

if pending:
    first = pending[0]
    last  = pending[-1]
    print("\nPremière photo en attente : " + first.get("scheduled_at","?") + " — " + first.get("filename","?")[:30])
    print("Dernière photo en attente : " + last.get("scheduled_at","?") + " — " + last.get("filename","?")[:30])

    # Group by day
    by_day = {}
    for e in pending:
        day = e.get("scheduled_at","")[:10]
        by_day.setdefault(day, []).append(e)
    print("\nRépartition par jour (" + str(len(by_day)) + " jours) :")
    for day in sorted(by_day.keys()):
        entries = by_day[day]
        times = [e.get("scheduled_at","")[-8:-3] for e in entries]
        print("  " + day + " — " + str(len(entries)) + " posts — " + ", ".join(times[:6]))

    # Check if any should have been sent already
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M")
    overdue = [e for e in pending if e.get("scheduled_at","") <= now_str]
    if overdue:
        print("\n[!] " + str(len(overdue)) + " post(s) dont l'heure est passée — en cours d'envoi à OneUp")
    else:
        print("\nProchain envoi à OneUp : " + first.get("scheduled_at","?"))

print("\n--- Comptes utilisés ---")
acc_ids = set()
for e in pending:
    for a in e.get("account_ids", []):
        acc_ids.add(a)
print("IDs comptes : " + str(acc_ids))

ssh.close()
