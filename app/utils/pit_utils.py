"""pit_utils.py — Best Practice PIT (Pathology Information Transfer) file generation.

Generates and delivers PIT investigation files that BP polls from a shared folder.
The 301 segment carries the message body as RTF; BP renders it as an investigation result.

Public API:
    text2rtf(text)                         → RTF string
    generate_pit_report(patient, pit_type,
                        content, user)     → PIT file string
    pit_delivery(internal_id, content,
                 patient_name)             → bool
    send_as_pit(patient, pit_label,
                body, user)                → bool
"""
import os
import re
from datetime import datetime

from flask import current_app

from app.models.system_setting import SystemSetting
from app.repositories.patient_repository import _format_clinical_age


def text2rtf(textstring: str) -> str:
    """Convert plain text or basic Markdown to a single-line RTF string for PIT 301 segment."""
    if not textstring:
        return ""

    text = textstring.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
    lines = text.split('\n')
    processed = []
    for line in lines:
        line = re.sub(r'^#+\s+(.*)', r'\\b \1\\b0 ', line)
        line = re.sub(r'\*\*(.*?)\*\*', r'\\b \1\\b0 ', line)
        line = re.sub(r'\*(.*?)\*', r'\\i \1\\i0 ', line)
        line = re.sub(r'^\s*[-*]\s+(.*)', r'\\bullet  \1', line)
        if line.strip() == '---':
            line = '-' * 75
        processed.append(line)

    rtf_body = '\\par '.join(processed)
    rtf = (
        '{\\rtf1\\ansi\\deff0'
        '{\\fonttbl{\\f0\\fnil\\fcharset0 Arial;}}'
        '\\viewkind4\\uc1\\pard\\f0\\fs20 '
        + rtf_body
        + '}'
    )
    return rtf.replace('\n', ' ').replace('\r', '')


def generate_pit_report(patient: dict, pit_type: str, contentstring: str,
                        user, createddate: str | None = None) -> str:
    """Build a full PIT format string for a single report."""
    if createddate is None:
        createddate = datetime.now().strftime('%d/%m/%Y')

    lastname    = (patient.get('SURNAME')   or '').strip()
    firstname   = (patient.get('FIRSTNAME') or '').strip()
    internal_id = str(patient.get('INTERNALID') or '')

    dob_raw = str(patient.get('DOB') or '')
    # Convert YYYY-MM-DD to DD/MM/YYYY
    try:
        dob = datetime.strptime(dob_raw[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        dob = dob_raw

    age_val = 0
    try:
        age_str_raw = _format_clinical_age(dob_raw)
        age_val = int(''.join(filter(str.isdigit, age_str_raw)))
    except (ValueError, TypeError):
        pass
    age_str = ('00' + str(age_val))[-3:]

    gender_full = (patient.get('GENDER') or 'Unknown').strip()
    gender = gender_full[0].upper() if gender_full else 'U'

    mobile_raw = (patient.get('PHONE_MOBILE') or '').strip()
    telephone  = re.sub(r'[^\d]', '', mobile_raw)
    address    = (patient.get('ADDRESS') or '').strip()

    medicare_full   = (patient.get('MEDICARENO') or '').strip()
    medicare_number = medicare_full.split()[0] if medicare_full else ''

    _title       = (getattr(user, 'title', None) or '').strip()
    _name        = (getattr(user, 'display_name', None) or 'Unknown Provider').strip()
    display_name = f'{_title} {_name}'.strip() if _title else _name
    providerno   = (getattr(user, 'bpsdb_provider_no', None) or '').strip()
    if not providerno:
        providerno = '00000000'

    now_str      = datetime.now().strftime('%d/%m/%Y AT %H:%M:%S')
    name_field   = f'{firstname} {lastname}'
    username_32  = (display_name + ' ' * 32)[:32]
    username_50  = display_name[:32] + ' ' * max(0, 50 - len(display_name))
    # Pad to exactly 8 chars with a leading zero if short; truncate at 8 if somehow longer
    pno_8        = ('0' * 8 + providerno)[-8:]

    pit = (
        f'001 {display_name}  -  {pit_type} \n'
        f'002 {" " * 75}\n'
        f'003 Report Run Number: 00000   Created:{createddate} \n'
        f'004 Surgery:  Reports: {now_str}  to   {now_str}  \n'
        f'009 {"-" * 75}\n'
        f'010 {username_50}{pno_8} \n'
        f'019 {"-" * 75}\n'
        f'020 Your Ref.   Patient Name                   Lab Ref.        Test\n'
        f'021 {internal_id:<11} {name_field:<54}\n'
        f'029 {"-" * 75}\n'
        f'100 Start Patient :       {lastname}, {firstname} \n'
        f'101                       {address}    \n'
        f'104                       Birthdate: {dob}    Age: Y{age_str}   Sex: {gender}\n'
        f'105                       Telephone: {telephone}     \n'
        f'109 {" " * 64}\n'
        f'110 Your Reference :      {internal_id:<44}\n'
        f'112 Medicare Number:      {medicare_number[:10]} \n'
        f'123 Addressee :           {username_32}  {pno_8} \n'
        f'129  \n'
        f'200 Start of Result:\n'
        f'204 Collected :           {createddate} \n'
        f'205 Name of Test :        {pit_type} \n'
        f'206 Reported :            {createddate} \n'
        f'301 {contentstring}\n'
        f'319  \n'
        f'390 End of Report :\n'
        f'399 {"-" * 75}\n'
        f'999 END OF LISTING - Run Number:0000  {createddate}                \n'
    )
    return pit


def folder_problem(directory: str) -> str | None:
    """Why PIT files can't be written to this folder, or None when they can (ADR-161).

    The folder must already exist: it is where Best Practice's incoming share is mounted on this
    server. MedUI never creates it, so a mistyped or unmounted path fails instead of quietly
    filling a local folder BP never reads."""
    directory = (directory or '').strip()
    if not directory:
        return 'No PIT folder is set (Setup → Messaging).'
    if directory.startswith(('\\\\', '//')) or re.match(r'^[A-Za-z]:[\\/]', directory):
        return ('A Windows path (\\\\SERVER\\share or C:\\…) can\'t be written from this server. Mount the '
                'share on the server first and give the folder it is mounted at.')
    if not os.path.isabs(directory):
        return 'The PIT folder must be a full path, starting with /.'
    if not os.path.isdir(directory):
        return f'The PIT folder {directory} doesn\'t exist. Is the share mounted?'
    if not os.access(directory, os.W_OK):
        return f'MedUI can\'t write to the PIT folder {directory}. Is the share mounted, and writable?'
    return None


def pit_delivery(internal_id: int | str, pit_content: str,
                 patient_name: str) -> bool:
    """Write a PIT string to the configured export directory."""
    if not current_app.config.get('PIT_EXPORT_ENABLED', False):
        raise RuntimeError('PIT export is disabled for this installation.')
    try:
        directory = (SystemSetting.get('pit_export_path', '') or '').strip()
        problem = folder_problem(directory)
        if problem:
            current_app.logger.error('PIT delivery failed: %s', problem)
            return False

        timestamp = datetime.now().strftime('%d%m%Y%H%M%S')
        filename  = f'{patient_name}_COMMS_{timestamp}.pit'
        filepath  = os.path.join(directory, filename)

        with open(filepath, 'w', newline='\r\n', encoding='utf-8') as fh:
            fh.write(pit_content)

        current_app.logger.info('PIT file written: %s', filepath)
        return True

    except Exception as exc:
        current_app.logger.error('PIT delivery error: %s', exc)
        return False


def send_as_pit(patient: dict, pit_label: str, body: str, user,
                createddate: str | None = None) -> bool:
    """Convert body → RTF → PIT file → deliver to BP shared folder."""
    rtf         = text2rtf(body)
    pit_content = generate_pit_report(patient, pit_label, rtf, user, createddate=createddate)
    patient_name = (
        f"{(patient.get('SURNAME') or 'Unknown').strip()}_"
        f"{(patient.get('FIRSTNAME') or 'Unknown').strip()}"
    )
    return pit_delivery(patient.get('INTERNALID', ''), pit_content, patient_name)
