import os
import requests
import yaml
from jinja2 import FileSystemLoader, Environment

APACHE_CONFIG = './apache.yml'
VHOST_TEMPLATE = './vhost_template.j2'

APACHE_CONFIG_URL = 'https://raw.githubusercontent.com/thundernest/thundernest-ansible/master/vars/apache.yml'
VHOST_TEMPLATE_URL = 'https://raw.githubusercontent.com/thundernest/thundernest-ansible/master/vars/vhost_template.j2'

VHOST_CONFIG_OUT = './built/tb_vhosts.conf'

def comment_out_commands(commands, string):
    """ Goes through a given string and comments out command that are in the commands list. """
    for cmd in commands:
        string = string.replace(cmd, '#{}'.format(cmd))
    return string

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

    # Remove the chain
    config.pop('apache_certificate_chain_file')

    # Some commands that don't clash well with the current apache setup.
    comment_out = [
        'Listen 443', # Already done
        'LoadModule', # Already done
        # FIXME: Errors due to file/folder not found, yet the folder is there..
        'ErrorLog',
        'CustomLog',
    ]

    vhosts = config.get('apache_vhosts')
    for (index, vhost_entry) in enumerate(vhosts):
        server_name = vhost_entry.get('servername')
        server_alias = vhost_entry.get('serveralias')
        extra_params = vhost_entry.get('extra_parameters')
        # Change servername and serveralias (if avail) from .net to .test
        if server_name is not None:
            vhosts[index]['servername'] = server_name.replace('.net', '.test')
        if server_alias is not None:
            vhosts[index]['serveralias'] = server_alias.replace('.net', '.test')
        if extra_params is not None:
            vhosts[index]['extra_parameters'] = comment_out_commands(comment_out, extra_params)
        else:
            # Fix a small issue where None (type) is displayed
            vhosts[index]['extra_parameters'] = ''

    # Set our modified config
    config.update({'apache_vhosts': vhosts})

    # Remove some problematic config values
    global_vhost_settings = comment_out_commands(comment_out, config.get('apache_global_vhost_settings'))
    config.update({'apache_global_vhost_settings': global_vhost_settings})

    # Do the render
    env.globals.update(**config)
    template = env.get_template(VHOST_TEMPLATE)
    template_str = template.render()

    if template_str == '':
        print("Error: Rendered template is empty")
        return

    with open(VHOST_CONFIG_OUT, 'w') as fh:
        fh.write(template_str)

def main():
    # Ensure we can use relative paths
    os.chdir(os.path.dirname(__file__))

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