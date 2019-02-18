import sys
import json

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Script command line tool.')
    parser.add_argument('tag', metavar='c17598.cybro_iw03', nargs='?',
                       help='Tag value name')
    parser.add_argument('--value', nargs='?', default='None',
                       help='Tag value to set')

    args = parser.parse_args()
    # print args

    data = {}
    data['tag'] = args.tag
    data['value'] = args.value
    json_data = json.dumps(data)
    print json_data