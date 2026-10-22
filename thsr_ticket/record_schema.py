"""Version contract for local booking records; legacy objects remain readable."""


class RecordVersionError(ValueError):
    pass


def validate_record(value):
    if not isinstance(value, dict):
        raise ValueError('紀錄格式必須是 JSON 物件。')
    version = value.get('_record_version', 1)
    if type(version) is not int or version != 1:
        raise RecordVersionError('此紀錄版本不支援；請更新程式，原始紀錄已保留。')
    return value
