"""
salesforce.py — Pull emails from Salesforce by Case or Opportunity number.
"""

import os
from typing import List, Optional
from datetime import datetime

from ingestion.msg_parser import EmailRecord

try:
    from simple_salesforce import Salesforce
except ImportError:
    Salesforce = None


def connect_salesforce(config: dict) -> Optional[object]:
    """Connect to Salesforce using credentials from config."""
    if Salesforce is None:
        print("[WARN] simple-salesforce not installed. Skipping SF pull.")
        return None

    sf_config = config.get("salesforce", {})
    username = sf_config.get("username", "")
    password = sf_config.get("password", "")
    token = sf_config.get("security_token", "")
    domain = sf_config.get("domain", "login")

    if not username or not password:
        print("[INFO] Salesforce credentials not configured. Skipping SF pull.")
        return None

    try:
        sf = Salesforce(
            username=username,
            password=password,
            security_token=token,
            domain=domain,
        )
        print("[INFO] Connected to Salesforce successfully.")
        return sf
    except Exception as e:
        print(f"[ERROR] Salesforce connection failed: {e}")
        return None


def pull_emails_by_case(sf, case_number: str) -> List[EmailRecord]:
    """Pull EmailMessage records linked to a Salesforce Case."""
    records = []

    try:
        # Find the Case ID
        result = sf.query(
            f"SELECT Id FROM Case WHERE CaseNumber = '{case_number}'"
        )
        if not result["records"]:
            print(f"[WARN] Case {case_number} not found in Salesforce.")
            return records

        case_id = result["records"][0]["Id"]

        # Pull EmailMessages linked to this Case
        emails = sf.query(
            f"""SELECT Id, FromAddress, FromName, ToAddress, CcAddress,
                       Subject, TextBody, MessageDate
                FROM EmailMessage
                WHERE ParentId = '{case_id}'
                ORDER BY MessageDate ASC"""
        )

        for em in emails["records"]:
            email_date = None
            if em.get("MessageDate"):
                try:
                    email_date = datetime.fromisoformat(
                        em["MessageDate"].replace("Z", "+00:00")
                    )
                except Exception:
                    pass

            to_list = []
            if em.get("ToAddress"):
                to_list = [a.strip() for a in em["ToAddress"].split(";") if a.strip()]

            cc_list = []
            if em.get("CcAddress"):
                cc_list = [a.strip() for a in em["CcAddress"].split(";") if a.strip()]

            record = EmailRecord(
                sender_name=em.get("FromName", ""),
                sender_email=em.get("FromAddress", ""),
                recipients=to_list,
                cc=cc_list,
                date=email_date,
                subject=em.get("Subject", ""),
                body=em.get("TextBody", ""),
                source_file=f"SF-Case-{case_number}",
                message_id=em.get("Id", ""),
            )
            records.append(record)

        print(f"[INFO] Pulled {len(records)} email(s) from Case {case_number}")

    except Exception as e:
        print(f"[ERROR] Failed to pull emails from Salesforce: {e}")

    return records


def pull_emails_by_opportunity(sf, opp_name: str) -> List[EmailRecord]:
    """Pull EmailMessage records linked to a Salesforce Opportunity."""
    records = []

    try:
        result = sf.query(
            f"SELECT Id FROM Opportunity WHERE Name = '{opp_name}'"
        )
        if not result["records"]:
            print(f"[WARN] Opportunity '{opp_name}' not found in Salesforce.")
            return records

        opp_id = result["records"][0]["Id"]

        emails = sf.query(
            f"""SELECT Id, FromAddress, FromName, ToAddress, CcAddress,
                       Subject, TextBody, MessageDate
                FROM EmailMessage
                WHERE RelatedToId = '{opp_id}'
                ORDER BY MessageDate ASC"""
        )

        for em in emails["records"]:
            email_date = None
            if em.get("MessageDate"):
                try:
                    email_date = datetime.fromisoformat(
                        em["MessageDate"].replace("Z", "+00:00")
                    )
                except Exception:
                    pass

            to_list = []
            if em.get("ToAddress"):
                to_list = [a.strip() for a in em["ToAddress"].split(";") if a.strip()]

            cc_list = []
            if em.get("CcAddress"):
                cc_list = [a.strip() for a in em["CcAddress"].split(";") if a.strip()]

            record = EmailRecord(
                sender_name=em.get("FromName", ""),
                sender_email=em.get("FromAddress", ""),
                recipients=to_list,
                cc=cc_list,
                date=email_date,
                subject=em.get("Subject", ""),
                body=em.get("TextBody", ""),
                source_file=f"SF-Opp-{opp_name}",
                message_id=em.get("Id", ""),
            )
            records.append(record)

        print(f"[INFO] Pulled {len(records)} email(s) from Opportunity '{opp_name}'")

    except Exception as e:
        print(f"[ERROR] Failed to pull emails from Salesforce: {e}")

    return records
