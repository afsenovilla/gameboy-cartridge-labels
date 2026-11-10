import json
print("%-20s %-4s %-6s | %-26s | %-26s | %-26s" % ("run", "shell", "part", "K=1 med/<=.25/>1mm", "K=8 med/<=.25/>1mm", "scale+-10% K=8"))
for l in open('results.jsonl'):
    r = json.loads(l); a = r['args']
    for part in ('recess', 'label'):
        if part not in r['eval']: continue
        e, j = r['eval'][part], r['eval'][part + ' scale+-10%']
        f = lambda v: "%.3f  %4.1f%%  %4.2f%%" % (v['median'], 100 * v['le0.25'], 100 * v['gt1'])
        print("%-20s %-4s %-6s | %-26s | %-26s | %-26s" % (a['tag'], a['shell'], part, f(e['1']), f(e['8']), f(j['8'])))
