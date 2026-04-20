import sys

from radar_app import legacy_app as _legacy_app

app = _legacy_app.app
db = _legacy_app.db
create_app = _legacy_app.create_app

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    sys.modules[__name__] = _legacy_app
