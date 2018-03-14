import sys
sys.path.append('..')
import settings
import subprocess

def execute(command, shell=False, env={}):
    command = command.split()
    global failures
    proc = subprocess.Popen(command, stderr=subprocess.STDOUT, shell=shell, env=env, universal_newlines=True)
    if proc.stdout:
        for line in iter(proc.stdout.readline, ""):
            yield line
        proc.stdout.close()
    return_code = proc.wait()
    if return_code:
            raise subprocess.CalledProcessError(return_code, command)
    print '\n'

for lang in settings.PROD_LANGUAGES:
    mkd = 'mkdir ../newlocale/{0} ../newlocale/{0}/LC_MESSAGES'.format(lang)
    init = 'msginit --no-translator --input=../messages.pot --locale={0} --output=../newlocale/{0}/LC_MESSAGES/messages.po'.format(lang)

    for line in execute(mkd):
        print mkd
        print line

    for line in execute(init):
        print init
        print line
