import requests
import yaml
from jinja2 import FileSystemLoader, Environment

APACHE_CONFIG = 'apache.yml'
VHOST_TEMPLATE = 'vhost_template.j2'

APACHE_CONFIG_URL = 'https://raw.githubusercontent.com/thundernest/thundernest-ansible/master/vars/apache.yml'
VHOST_TEMPLATE_URL = 'https://raw.githubusercontent.com/thundernest/thundernest-ansible/master/vars/vhost_template.j2'

VHOST_CONFIG_OUT = './built/tb_vhosts.conf'

def render_config(config_contents):
    """ Pulls in the apache config, updates some things for local development, and renders it out. """
    print("Rendering...")

    load = FileSystemLoader('./')
    env = Environment(loader=load, lstrip_blocks=True, trim_blocks=True)

    config = yaml.load(config_contents, yaml.Loader)

    # Missing defaults
    config.update({'apache_ignore_missing_ssl_certificate': True})
    config.update({'apache_listen_ip': '*'})
    config.update({'apache_listen_port': '80'})
    config.update({'apache_listen_port_ssl': '443'})
    config.update({'apache_ssl_cipher_suite': 'DEFAULT'})
    config.update({'apache_ssl_protocol': 'TLSv1.3'})

    # Use our ssl keys
    config.update({'apache_certificate_key_file': '/etc/apache2/ssl/ssl.key'})
    config.update({'apache_certificate_file': '/etc/apache2/ssl/ssl.crt'})

    # Let's only pull in thunderbird.net and start.thunderbird.net for now...
    vhosts = config.get('apache_vhosts')
    vhosts = filter(lambda host: 'www.thunderbird.net' in host['servername']
                                 or 'start.thunderbird.net' in host['servername'], vhosts)

    config.update({'apache_vhosts': list(vhosts)})

    # Do the render
    env.globals.update(**config)
    template = env.get_template(VHOST_TEMPLATE)
    template_str = template.render()

    if template_str == '':
        print("Error: Rendered template is empty")
        return

    # Some commands we don't need or conflict with existing config
    comment_out = [
        'SSLCertificateChainFile',
        'Listen 443',
        'LoadModule',
    ]
    for cmd in comment_out:
        template_str = template_str.replace(cmd, '#{}'.format(cmd))

    # Rename .net tlds to .test
    template_str = template_str.replace('.net', '.test')
    # and fix the directories
    template_str = template_str.replace('start/thunderbird.test', 'start/thunderbird.net')

    with open(VHOST_CONFIG_OUT, 'w') as fh:
        fh.write(template_str)

def main():
    print("Retrieving apache.yml from thundernest-ansible.")
    config = requests.get(APACHE_CONFIG_URL)
    # Save a local copy for reference
    with open(APACHE_CONFIG, 'wb') as fh:
        fh.write(config.content)

    print("Retrieving vhost_template.j2 from thundernest-ansible.")
    template = requests.get(VHOST_TEMPLATE_URL)
    # Save a local copy for reference
    with open(VHOST_TEMPLATE, 'wb') as fh:
        fh.write(template.content)

    render_config(config.content)

    print("Done!")

if __name__ == '__main__':
    main()