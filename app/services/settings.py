from app.extensions import db
from app.models.site_setting import SiteSetting


def get_setting(key, default=None):
    setting = SiteSetting.query.filter_by(key=key).first()
    return setting.value if setting else default


def set_setting(key, value):
    setting = SiteSetting.query.filter_by(key=key).first()
    if not setting:
        setting = SiteSetting(key=key, value=str(value))
        db.session.add(setting)
    else:
        setting.value = str(value)
    db.session.commit()
    return setting
