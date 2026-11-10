# Copyright (c) 2026, eCentric and contributors
"""p004: chay LAI p003 (chuyen phieu Data Request cu sang /du-lieu) sau hotfix 10/11/2026.

Lan deploy dau, p003 buoc "migrate" loi TypeError trong repository.rule_set (dict(child_doc) -
'ECDataSLARuleItem' object is not iterable), _try nuot loi -> chua phieu cu nao duoc chuyen (buoc
doi route the Data Request da chay xong truoc do). Hotfix sua rule_set; patch nay goi lai dung
p003.execute(): chay lai an toan (phieu da co ticket bo qua, route da doi khong ghi), FAIL-SAFE nhu p003.
"""


def execute():
    from ecentric_workspace.data_hub.patches import p003_chuyen_phieu_data_request_cu as p003
    p003.execute()
