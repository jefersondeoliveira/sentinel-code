# test_detectors.py
from tools.java.file_reader import read_java_files, read_application_properties
from tools.java.issue_detectors import detect_n_plus_one, detect_missing_cache, detect_connection_pool

files = read_java_files('sample_project')
configs = read_application_properties('sample_project')

n1 = detect_n_plus_one(files)
cache = detect_missing_cache(files)
pool = detect_connection_pool(configs)

all_issues = n1 + cache + pool
print(f'Issues encontrados: {len(all_issues)}')
for issue in all_issues:
    print(str(issue))