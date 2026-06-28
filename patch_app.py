import re

with open("group_1_plane_dashboard/app.py", "r") as f:
    app_py = f.read()

with open("/tmp/my_updates_app.py", "r") as f:
    my_app = f.read()

# Replace the imports
# from analysis.staff import (...)
staff_import_re = re.compile(r'from analysis\.staff import \([\s\S]*?\)', re.MULTILINE)
my_staff_import = staff_import_re.search(my_app).group(0)
app_py = staff_import_re.sub(my_staff_import, app_py)

# Replace get_staff_data
get_staff_data_re = re.compile(r'@st\.cache_data\ndef get_staff_data\(\) -> .*?\n.*?\n.*?\n.*?\n.*?\n', re.MULTILINE)
my_get_staff_data = get_staff_data_re.search(my_app).group(0)
# Wait, let's just use string replacement for get_staff_data since regex might be tricky
old_get_staff_data = """@st.cache_data
def get_staff_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    needed = [DATA_DIR / "staff_flights.parquet", DATA_DIR / "crew_gaps.parquet"]
    if not all(p.exists() for p in needed):
        with st.spinner("Loading staff data from database (first run only)..."):
            db_staff.fetch_and_save()
    return load_staff_flights(), load_crew_gaps()"""

new_get_staff_data = """@st.cache_data
def get_staff_data() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    needed = [
        DATA_DIR / "q1_staff_counts.parquet", 
        DATA_DIR / "q2_staff_assignments.parquet", 
        DATA_DIR / "q3_staff_usage.parquet"
    ]
    if not all(p.exists() for p in needed):
        st.error("Missing staff data Parquet files. Please run the extraction script manually (e.g. `python -m db.staff`) before using the dashboard.")
        st.stop()
    return load_staff_counts(), load_staff_assignments(), load_staff_usage()"""

app_py = app_py.replace(old_get_staff_data, new_get_staff_data)

# Replace TAB 2
tab2_re = re.compile(r'# TAB 2 — Staff Occupation\n# ══════════════════════════════════════════════════════════════════════════════\n\nwith tab2:[\s\S]*?(?=# ══════════════════════════════════════════════════════════════════════════════\n# TAB 3)', re.MULTILINE)

my_tab2 = tab2_re.search(my_app).group(0)
app_py = tab2_re.sub(my_tab2, app_py)

with open("group_1_plane_dashboard/app.py", "w") as f:
    f.write(app_py)

print("Patched app.py")
