import json
import os


def get_path_config():
    restrictions = json.loads(os.environ.get('ACCESS_RESTRICTIONS', '{}'))
    result = ''
    if '/' not in restrictions:
        restrictions['/'] = {}

    client_cert_used = any(map(
        lambda config: 'client-cert' in config,
        restrictions.values()
    ))

    if client_cert_used:
        result += """
location /client-cert-check-internal {
    internal;
    if ($http_x_client_certificate) {
        return 200;
    }
    return 403;
}

"""

    for path, config in restrictions.iteritems():
        if path in ['/_mxadmin/']:
            raise Exception(
                'Can not override access restrictions on system path %s' % path
            )
        satisfy = 'all'
        if 'satisfy' in config:
            if config['satisfy'] in ['any', 'all']:
                satisfy = config['satisfy']
            else:
                raise Exception(
                    'invalid satisfy value: %s' % config['satisfy']
                )
        ipfilter = []
        if 'ipfilter' in config:
            for ip in config['ipfilter']:
                ipfilter.append('allow ' + ip + ';')
            ipfilter.append('deny all;')
        client_cert = ''
        if 'client-cert' in config:
            client_cert = 'auth_request /client-cert-check-internal;'

        result += """
location %s {
    if ($request_uri ~ ^/(.*\.(css|js)|forms/.*|img/.*|pages/.*)\?[0-9]+$) {
        expires 1y;
    }
    proxy_pass http://mendix;
    satisfy %s;
    %s
    %s
}
        """ % (
            path,
            satisfy,
            '\n        '.join(ipfilter),
            client_cert,
        )
        return '\n    '.join(result.split('\n'))

if __name__ == '__main__':
    print get_path_config()
