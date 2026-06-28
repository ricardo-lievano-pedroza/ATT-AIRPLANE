import re

with open("group_1_plane_dashboard/app.py", "r") as f:
    app_py = f.read()

with open("/tmp/my_updates_app.py", "r") as f:
    my_app = f.read()

# Replace TAB 2
tab2_re = re.compile(r'# TAB 2 — Staff Occupation\n# ══════════════════════════════════════════════════════════════════════════════\n\nwith tab2:[\s\S]*?(?=# ══════════════════════════════════════════════════════════════════════════════\n# TAB 3)', re.MULTILINE)

my_tab2 = tab2_re.search(my_app).group(0)

# In the current app.py, the regex above will fail because `with tab2:` is commented out as `# with tab2:`.
current_tab2_re = re.compile(r'# TAB 2 — Staff Occupation\n# ══════════════════════════════════════════════════════════════════════════════\n\n# with tab2:[\s\S]*?(?=# ══════════════════════════════════════════════════════════════════════════════\n# TAB 3)', re.MULTILINE)

app_py = current_tab2_re.sub(my_tab2, app_py)

with open("group_1_plane_dashboard/app.py", "w") as f:
    f.write(app_py)

print("Patched TAB 2")
