import tempfile,pathlib,subprocess,os,json,time
D=pathlib.Path(__file__).resolve().parent/'submission';checks=[]
with tempfile.TemporaryDirectory(prefix='dual_unit_') as tmp:
 root=pathlib.Path(tmp)/'repo';root.mkdir();store=pathlib.Path(tmp)/'store';env=dict(os.environ,DUAL_TEST_WORKSPACE=str(root),DUAL_TEST_STORE=str(store))
 def git(*args):return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True)
 git('init');git('config','user.email','test@example.invalid');git('config','user.name','test');(root/'value.py').write_text('value = 0\n');(root/'tests').mkdir();(root/'tests/test_value.py').write_text('original\n');git('add','.');git('commit','-m','baseline')
 def run(role,**kw):
  args=['python3',str(D/'skills'/role/'scripts/control.py')]
  for k,v in kw.items():args += ['--'+k,str(v)]
  r=subprocess.run(args,env=env,capture_output=True,text=True,timeout=15);assert r.returncode==0,r.stdout+r.stderr;return json.loads(r.stdout)
 run('candidate-a',action='exec',command="printf 'value = 1\\n' > value.py; printf 'new\\n' > added.txt; printf 'tampered\\n' > tests/test_value.py")
 assert (root/'value.py').read_text()=='value = 1\n';assert (root/'tests/test_value.py').read_text()=='original\n';checks.append('fallback_and_protected_test_filter')
 state=json.loads((store/'state.json').read_text());am=json.loads((store/'A/meta.json').read_text());assert abs(am['deadline']-state['started']-720)<0.01
 state['started']-=480;(store/'state.json').write_text(json.dumps(state))
 run('candidate-b',action='status');bm=json.loads((store/'B/meta.json').read_text());assert abs(bm['deadline']-state['started']-720)<0.01;checks.append('both_candidates_shared_12_minute_deadline')
 r=run('candidate-b',action='exec',command='cat value.py; test ! -e added.txt');assert r['exit_code']==0 and 'value = 0' in r['output'];checks.append('B_clean_baseline_after_A_fallback')
 report='I changed value.py. Test command: python value.py. This fixture report is supplied by the test caller.'
 run('candidate-a',action='finish',report=report);assert (store/'A/report.md').read_text()==report;assert json.loads((store/'A/report_provenance.json').read_text())['author']=='solver_A';checks.append('exact_report_preservation')
 r=run('candidate-a',action='exec',command='rm value.py');assert 'error' in r;checks.append('finished_candidate_frozen')
 run('candidate-b',action='exec',command="printf 'value = 2\\n' > value.py")
 m=json.loads((store/'B/meta.json').read_text());m['deadline']=time.monotonic()+.2;(store/'B/meta.json').write_text(json.dumps(m));r=run('candidate-b',action='exec',command="sleep 2; printf 'late\\n' > value.py");assert r['exit_code']==124;assert (store/'B/repo/value.py').read_text()=='value = 2\n';checks.append('command_deadline_kills_before_late_edit')
 run('candidate-b',action='finish',report='B independently wrote this report after its operation deadline.');checks.append('report_allowed_after_operation_timeout')
 run('patch-judge',action='select',candidate='B');assert (root/'value.py').read_text()=='value = 2\n' and not (root/'added.txt').exists();checks.append('selection_exact_and_removes_A_only_new_file')
 run('patch-judge',action='select',candidate='A');assert (root/'value.py').read_text()=='value = 1\n' and (root/'added.txt').exists();checks.append('selection_can_switch_back')
 a=run('patch-judge',action='inspect',candidate='A',part='report',limit=15);b=run('patch-judge',action='inspect',candidate='A',part='report',offset=a['next_offset']);assert a['content']+b['content']==report;checks.append('lossless_report_pagination')
 # A new candidate store tests private continuation without changing the first fixture.
 store=pathlib.Path(tmp)/'segments';env['DUAL_TEST_STORE']=str(store)
 r=run('candidate-a',action='begin');assert r['segment']==1
 for _ in range(8):assert run('candidate-a',action='exec',command='true')['exit_code']==0
 assert 'error' in run('candidate-a',action='exec',command='true')
 note='Solver A wrote its own continuation: inspected code; no final conclusion.'
 run('candidate-a',action='checkpoint',report=note)
 r=run('candidate-a',action='begin');assert r['segment']==2 and r['segment_calls_remaining']==8 and r['own_previous_report']==note
 checks.append('segment_cap_and_exact_own_continuation')
 r=run('candidate-b',action='begin');assert r['own_previous_report'] is None
 checks.append('B_continuation_store_excludes_A_report')
print(json.dumps({'passed':checks,'count':len(checks)},indent=2));(D.parent/'control_tests.json').write_text(json.dumps({'passed':checks,'count':len(checks)},indent=2))
