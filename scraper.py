import requests
import re
import time
from typing import List, Dict, Any

# Headers to mimic a browser request
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def fetch_with_requests(url: str) -> str:
    """
    Fetches the content of the specified URL using requests.
    :param url: The URL to fetch.
    :return: The HTML content as a string.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as error:
        print(f'Error fetching content: {error}')
        raise error

def clean_translated_text(text: str) -> str:
    """
    Cleans HTML text by removing common translation wrappers like <font dir="auto" style="...">.
    Repeatedly removes font tags until none left.
    :param text: The text to clean.
    :return: Cleaned text.
    """
    if not isinstance(text, str):
        return ''

    def remove_fonts(match):
        inner = re.sub(r'<font[^>]*>', '', re.sub(r'</font>', '', match.group(0)))
        return clean_translated_text(inner)

    while True:
        new_cleaned = re.sub(r'<font[^>]*>.*?</font>', remove_fonts, text, flags=re.DOTALL | re.IGNORECASE)
        if new_cleaned == text:
            break
        text = new_cleaned

    text = re.sub(r'<[^>]+>', '', text)  # Remove remaining tags
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    return text.strip()

def extract_provisions_from_html(html: str) -> List[Dict[str, str]]:
    """
    Extracts individual provision objects {url, title, org} from the list page HTML using regular expressions.
    :param html: The HTML content of the list page.
    :return: Array of provision objects.
    """
    provisions = []
    item_regex = re.compile(
        r'<div class=["\']ResultaatItem["\']>[\s\S]*?<div class=["\']ResultaatTitel["\']><a href="([^"]+)"[^>]*name="anr1"[^>]*>([^<]+)</a></div>[\s\S]*?<span class=["\']notranslate["\']>([^<]+)</span>[\s\S]*?</div>',
        re.DOTALL
    )
    for match in item_regex.finditer(html):
        url = match.group(1).strip() if match.group(1) else ''
        title = match.group(2).strip() if match.group(2) else ''
        org = match.group(3).strip() if match.group(3) else ''
        if url and title and org and not any(p['url'] == url for p in provisions):
            provisions.append({'url': url, 'title': title, 'org': org})
    return provisions

def extract_total_provisions(html: str) -> int:
    """
    Extracts the total number of provisions from the list page HTML.
    :param html: The HTML content of the list page.
    :return: Total provisions count.
    """
    total_match = re.search(r'([\d,]+)\s+voorzieningen gevonden', html)
    if total_match and total_match.group(1):
        return int(total_match.group(1).replace(',', ''))
    return 0

def get_paginated_url(base_url: str, page_num: int) -> str:
    """
    Generates the paginated URL for a given page number.
    :param base_url: The base URL.
    :param page_num: The page number.
    :return: The full URL for the page.
    """
    if page_num == 1:
        return base_url
    return f'{base_url}?p={page_num}'

def extract_provision_details(html: str) -> Dict[str, Any]:
    """
    Extracts structured details from an individual provision page HTML.
    Handles potential translation artifacts by cleaning text and flexible label matching with inner content.
    Also extracts address/contact info from #dbsContactPane.
    :param html: The HTML content.
    :return: Details object with original language fields.
    """
    details = {
        'title': '',
        'org': '',
        'purpose': '',
        'moreInfo': '',
        'targetGroup': '',
        'mission': '',
        'contact': {'visitingAddress': '', 'postalAddress': '', 'phone': '', 'email': '', 'website': ''}
    }

    # Title
    title_match = (re.search(r'<h1 class=["\']notranslate["\']>([^<]+)</h1>', html) or
                   re.search(r'<title>([^<]+) - [^<]+ - Voorzieningen\.nl</title>', html))
    if title_match and title_match.group(1):
        details['title'] = clean_translated_text(title_match.group(1))

    # Organization name
    org_match = (re.search(r'<h2 class=["\']notranslate["\']><a[^>]*>([^<]+)</a></h2>', html) or
                 re.search(r'<h2>([^<]+)</h2>', html))
    if org_match and org_match.group(1):
        details['org'] = clean_translated_text(org_match.group(1))

    # Purpose (Doel / Goal)
    purpose_match = re.search(r'<h3>(Doel|Goal)</h3>\s*<span class=[\'"]doel[\'"]>([\s\S]*?)</span>', html, re.IGNORECASE)
    if purpose_match and purpose_match.group(2):
        details['purpose'] = clean_translated_text(purpose_match.group(2))

    # More information
    more_info_match = re.search(r'<h3>(Meer informatie|More information)</h3>\s*<a href="([^"]+)"[^>]*>([^<]*)</a>', html, re.IGNORECASE)
    if more_info_match:
        details['moreInfo'] = clean_translated_text(more_info_match.group(3)) or more_info_match.group(2)

    # Target Group (Doelgroep)
    target_match = re.search(r'<h3>(Doelgroep|Target audience)</h3>\s*([\s\S]*?)(?=<h3>|</div>)', html, re.IGNORECASE)
    if target_match and target_match.group(2):
        details['targetGroup'] = clean_translated_text(target_match.group(2))

    # Mission
    mission_match = re.search(r'<b>(Doelstelling of kernactiviteit|Objective or core activity)[\s:]*</b>\s*<br>([\s\S]*?)</p>', html, re.IGNORECASE | re.DOTALL)
    if mission_match and mission_match.group(2):
        details['mission'] = clean_translated_text(mission_match.group(2))

    # Extract contact information from dbsContactPane
    contact_section_match = re.search(r'<div[^>]*id=[\'"]dbsContactPane[\'"][^>]*>([\s\S]*?)</div>\s*</div>\s*</div>', html, re.IGNORECASE | re.DOTALL)
    if contact_section_match and contact_section_match.group(1):
        contact_html = contact_section_match.group(1)

        # Visiting address
        visiting_section = re.search(r'<b[^>]*>(Visiting address|Bezoekadres):</b>([\s\S]*?)(?=<b|</div>)', contact_html, re.IGNORECASE | re.DOTALL)
        if visiting_section and visiting_section.group(2):
            lines = re.sub(r'<br\s*?/?>', ', ', visiting_section.group(2))
            lines = re.sub(r'<[^>]+>', '', lines)
            lines = re.sub(r'\s+', ' ', lines)
            details['contact']['visitingAddress'] = lines.strip()

        # Postal address
        postal_section = re.search(r'<b[^>]*>(Postal address|Postadres):</b>([\s\S]*?)(?=<b|</div>)', contact_html, re.IGNORECASE | re.DOTALL)
        if postal_section and postal_section.group(2):
            lines = re.sub(r'<br\s*?/?>', ', ', postal_section.group(2))
            lines = re.sub(r'<[^>]+>', '', lines)
            lines = re.sub(r'\s+', ' ', lines)
            details['contact']['postalAddress'] = lines.strip()

        # Phone number
        phone_match = re.search(r'<b[^>]*>(Phone number|Telefoonnummer):</b>\s*([^<]+)', contact_html, re.IGNORECASE)
        if phone_match and phone_match.group(2):
            details['contact']['phone'] = clean_translated_text(phone_match.group(2))

        # Email
        email_match = re.search(r'mailto:([^"\']+)', contact_html, re.IGNORECASE)
        if email_match:
            details['contact']['email'] = email_match.group(1).strip()

        # Website
        website_match = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>\s*(?:www\.[^<]+|[^<]+)</a>', contact_html, re.IGNORECASE)
        if website_match:
            details['contact']['website'] = website_match.group(1).strip()

    return details

def append_provision_to_md(file_path: str, provision: Dict[str, str], details: Dict[str, Any]) -> None:
    """
    Appends a markdown section for a provision to the file using extracted details in original language.
    :param file_path: The MD file path.
    :param provision: The provision object with url, title, org.
    :param details: The extracted details.
    """
    md_content = f'\n### {details["title"]}\n'
    md_content += f'**Organisatie:** {details["org"]}\n'
    md_content += f'**URL:** {provision["url"]}\n'

    if details['purpose']:
        md_content += f'\n**Doel:** {details["purpose"]}\n'
    if details['moreInfo']:
        md_content += f'\n**Meer informatie:** {details["moreInfo"]}\n'
    if details['targetGroup']:
        md_content += f'\n**Doelgroep:** {details["targetGroup"]}\n'
    if details['mission']:
        md_content += f'\n**Missie:** {details["mission"]}\n'

    md_content += '\n**Contactinformatie:**\n'
    if details['contact']['visitingAddress']:
        md_content += f'- Bezoekadres: {details["contact"]["visitingAddress"]}\n'
    if details['contact']['postalAddress']:
        md_content += f'- Postadres: {details["contact"]["postalAddress"]}\n'
    md_content += f'- Telefoon: {details["contact"]["phone"] or "N.v.t."}\n'
    md_content += f'- E-mail: {details["contact"]["email"] or "N.v.t."}\n'
    md_content += f'- Website: {details["contact"]["website"] or "N.v.t."}\n'
    md_content += '\n---\n'  # Separator

    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(md_content)

def fetch_and_save_all_provisions(initial_url: str) -> None:
    """
    Fetches content from the initial list page, extracts provision links dynamically across all paginated pages,
    fetches full details for each unique provision, and appends to a single .md file in original language.
    :param initial_url: The initial list page URL.
    """
    md_file_path = 'scraped_data/all_scraped_data.md'
    processed_urls = set()  # To track unique provisions
    page_num = 1
    has_more_pages = True
    total_provisions = 0

    try:
        print('Fetching initial list page to determine total...')
        initial_content = fetch_with_requests(initial_url)
        total_provisions = extract_total_provisions(initial_content)
        print(f'Total provisions found: {total_provisions}')

        # Initialize MD file
        with open(md_file_path, 'w', encoding='utf-8') as f:
            f.write('# Alle Voorzieningen Details (in originele taal)\n\n')

        while has_more_pages:
            page_url = get_paginated_url(initial_url, page_num)
            print(f'\nFetching page {page_num}: {page_url}')
            page_content = fetch_with_requests(page_url)
            page_provisions = extract_provisions_from_html(page_content)

            print(f'Page {page_num} yielded {len(page_provisions)} provisions.')

            if len(page_provisions) == 0:
                has_more_pages = False
                print('No more provisions; stopping pagination.')
            else:
                # Process each new provision
                for prov in page_provisions:
                    if prov['url'] not in processed_urls:
                        processed_urls.add(prov['url'])
                        try:
                            print(f'Processing unique provision: {prov["title"]} by {prov["org"]}')
                            full_content = fetch_with_requests(prov['url'])
                            details = extract_provision_details(full_content)
                            append_provision_to_md(md_file_path, prov, details)
                            print(f'Added details for {details["title"]} (Total processed: {len(processed_urls)}).')
                        except Exception as error:
                            print(f'Failed to process {prov["title"]}: {error}')

                        # Delay for details fetch
                        time.sleep(1)

                page_num += 1
                # Delay between pages
                time.sleep(2)

        print(f'\nAll {len(processed_urls)} unique provisions processed and saved to {md_file_path}.')
    except Exception as error:
        print(f'Error in fetch_and_save_all_provisions: {error}')
        raise error

# Usage
if __name__ == '__main__':
    initial_url = 'https://voorzieningen.nl/totaal/aanbod.html'
    fetch_and_save_all_provisions(initial_url)