# Copyright (c) 2026, eCentric and contributors
"""Dua lai len SharePoint cac phieu Contract Review DA GUI ma chua co lien ket nao (20/11/2026).

VI SAO: createLink(scope=users) tra 400 noResolvedUsers khi MOT dia chi trong luong khong co tai khoan
Microsoft 365 -> ca lo hong -> tep da tai len nhung khong ghi lien ket, .docx khong "Mo online".
EC-CTR-2026-00122 va moi phieu cua anh.luu tu 09/10 (00042 ... 00122) bi vay. Ban sua cung deploy nay:
cap_quyen cap tung nguoi khi gap loi do (nguoi hong vao bo_qua + log).

CACH LAM: dung lai dung p194 (CHI dat viec vao hang doi `long`, khong goi Graph trong migrate; chi phieu
co dinh kem + da gui + chua co lien ket; tran 200; khong bao gio nem loi).
"""


def execute():
    from ecentric_workspace.approval_center.patches import p194_backfill_contract_sharepoint as p194
    p194.execute()
