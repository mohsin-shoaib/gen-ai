# import subprocess
# import json
# import os
# import re
# from urllib.parse import urljoin, urlparse
# from datetime import datetime
# import time

# BASE_URL = 'https://voorzieningen.nl'

# VUGHT_ORG_FILTER = 'leergeld-vught'  # Retained for URL check logic, but not hardcoded in JSON

# def normalize_url(href):
#     if href.startswith('http'):
#         return href
#     return urljoin(BASE_URL, href)

# def fetch_page(url):
#     try:
#         cmd = ['curl', '-s', '-A', 'Mozilla/5.0 (compatible; Scraper)', url]
#         result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
#         result.check_returncode()
#         return result.stdout
#     except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
#         print(f"Error fetching {url}: {error}")
#         return None

# def clean_text(text):
#     return re.sub(r'<.*?>', '', text).strip()

# def extract_details(html):
#     details = {
#         'heading': '',
#         'description': '',
#         'visiting_address': '',
#         'persons': [],
#         'other_info': {}
#     }

#     # Heading from <h1>
#     heading_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
#     details['heading'] = heading_match.group(1).strip() if heading_match else ''

#     # Description: Doel and Toelichting
#     doel_match = re.search(r'<h3>Doel</h3>\s*<p>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
#     doel = clean_text(doel_match.group(1)) if doel_match else ''
#     toel_match = re.search(r'<h3>Toelichting</h3>\s*<p>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
#     toel = clean_text(toel_match.group(1)) if toel_match else ''
#     details['description'] = f"Doel: {doel}\nToelichting: {toel}"

#     # Other info: Doelstelling
#     doelstelling_match = re.search(r'Doelstelling of kernactiviteit:</p>\s*<p>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
#     if doelstelling_match:
#         details['other_info']['doelstelling'] = clean_text(doelstelling_match.group(1))

#     # Contact person details
#     persons = []
#     name_match = re.search(r'<h3>Contactpersoon</h3>\s*<p>Naam:\s*([^<]+?)(?=<br>|<p|$)', html, re.IGNORECASE | re.DOTALL)
#     name = name_match.group(1).strip() if name_match else ''

#     phone_matches = re.findall(r'Telefoonnummer:\s*<a\s+href="tel:([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
#     phone = ', '.join([match[1].strip() for match in phone_matches]) if phone_matches else ''

#     email_matches = re.findall(r'E-mail:\s*<a\s+href="mailto:([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
#     email = ', '.join([match[1].strip() for match in email_matches]) if email_matches else ''

#     if name and (phone or email):
#         persons.append({
#             'name': name,
#             'phone': phone,
#             'email': email
#         })

#     # Addresses
#     # Adres (visiting)
#     address_match = re.search(r'<p><b>Adres:</b>?\s*<br ?/?>\s*([^<]+?)(?:<br ?/?><span[^>]*>([^<]+?)</span>)?</p>', html, re.IGNORECASE | re.DOTALL)
#     if address_match:
#         street = address_match.group(1).strip()
#         city_post = address_match.group(2).strip() if address_match.group(2) else ''
#         details['visiting_address'] = f"{street}, {city_post}" if city_post else street

#     # Bezoekadres alternative
#     if not details['visiting_address']:
#         bezoek_match = re.search(r'<p>Bezoekadres:</p>\s*<p>([^<]+)</p>\s*<p>([^<]+)</p>', html, re.IGNORECASE | re.DOTALL)
#         if bezoek_match:
#             details['visiting_address'] = f"{bezoek_match.group(1).strip()}, {bezoek_match.group(2).strip()}"

#     # Postal Address
#     postal_match = re.search(r'<p><b>Postadres:</b>?\s*<br ?/?>\s*([^<]+?)(?:<br ?/?><span[^>]*>([^<]+?)</span>)?</p>', html, re.IGNORECASE | re.DOTALL)
#     postal_address = ''
#     if postal_match:
#         street = postal_match.group(1).strip()
#         city_post = postal_match.group(2).strip() if postal_match.group(2) else ''
#         postal_address = f"{street}, {city_post}" if city_post else street
#     else:
#         # Alternative for Postadres
#         post_alt_match = re.search(r'<p>Postadres:</p>\s*<p>([^<]+)</p>\s*<p>([^<]+)</p>', html, re.IGNORECASE | re.DOTALL)
#         if post_alt_match:
#             postal_address = f"{post_alt_match.group(1).strip()}, {post_alt_match.group(2).strip()}"

#     if postal_address:
#         for person in persons:
#             person['postal_address'] = postal_address
#         if not persons:
#             # Add to org if no person
#             persons.append({'postal_address': postal_address})

#     # Website
#     website_match = re.search(r'Website:\s*<a\s+href="([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
#     website = website_match.group(1).strip() if website_match else ''
#     if website:
#         for person in persons:
#             person['website'] = website
#         if not persons:
#             persons.append({'website': website})

#     # Fallback: Organizational details if no person
#     if not persons:
#         title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
#         org_name = details['heading'] or (title_match.group(1).split(' - ')[0].strip() if title_match else 'Unknown Organization')

#         org_phone_matches = re.findall(r'<p[^>]*>Telefoonnummer:\s*([^\s<]+(?:\s-[^\s<]+)?)</p>', html, re.IGNORECASE)
#         org_phone = ', '.join([p.strip() for p in org_phone_matches]) if org_phone_matches else ''

#         org_email_match = re.search(r'E-mailadres:\s*<a\s+href="mailto:([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
#         org_email = org_email_match.group(1).strip() if org_email_match else ''

#         persons.append({
#             'name': org_name,
#             'phone': org_phone,
#             'email': org_email,
#             'address': details['visiting_address'],
#             'postal_address': postal_address,
#             'website': website
#         })

#     details['persons'] = persons

#     return details

# def append_to_md_file(main_topic, sub_topic, location, wpid, detail_url, details):
#     folder_path = os.path.join(os.getcwd(), 'scraped_data')
#     os.makedirs(folder_path, exist_ok=True)
#     filename = os.path.join(folder_path, 'all_scraped_data.md')

#     # Slug for reference
#     slug = os.path.basename(detail_url).replace('.html', '')

#     # Format as Markdown section
#     md_content = f"""

# # {main_topic}

# ## Subtopic: {sub_topic}

# ### Detail: {slug}

# | Field          | Value                  |
# |----------------|------------------------|
# | Name           | {details.get('persons', [{}])[0].get('name', 'N/A')} |
# | Phone          | {details.get('persons', [{}])[0].get('phone', 'N/A')} |
# | Email          | {details.get('persons', [{}])[0].get('email', 'N/A')} |
# | Visiting Address | {details.get('visiting_address', 'N/A')} |
# | Postal Address | {details.get('persons', [{}])[0].get('postal_address', 'N/A')} |
# | Website        | {details.get('persons', [{}])[0].get('website', 'N/A')} |

# **Heading:** {details.get('heading', 'N/A')}

# **Description:** {details.get('description', 'N/A')}

# **Other Info:** {details.get('other_info', {})}

# **Full Data:**\n```json\n{json.dumps(details, indent=2, ensure_ascii=False)}\n```

# **Source URL:** {detail_url}

# ---

# *Scraped on: {datetime.now().isoformat()}*"""

#     # Check if file exists; if not, add initial header
#     if not os.path.exists(filename):
#         header = f"# Scraped Data for {main_topic} - Filtered to {location} Municipality (wpid={wpid})\n\n"
#         with open(filename, 'w', encoding='utf-8') as f:
#             f.write(header + md_content)
#     else:
#         with open(filename, 'a', encoding='utf-8') as f:
#             f.write(md_content)

#     print(f"    Appended structured entry for {slug} to: {filename}")

# def scrape_site():
#     print('Starting scrape of main page...')
    
#     main_url = f'{BASE_URL}/bewegen/aanbod.html?wpid=2093'
#     main_html = fetch_page(main_url)
#     if not main_html:
#         print('Failed to fetch main page. Exiting.')
#         return
    
#     print(f'Fetched main page successfully.')
    
#     # Extract dynamic metadata from main_html and main_url
#     # Main topic from title
#     title_match = re.search(r'<title[^>]*>([^<]+)</title>', main_html, re.IGNORECASE)
#     main_topic = clean_text(title_match.group(1)) if title_match else 'Bewegen & Ontmoeten'
    
#     # Sub topic from <B>Lokale voorzieningen (XXX)</B>
#     sub_match = re.search(r'<B>([^<]+?)\s*\(\d+\)</B>', main_html, re.IGNORECASE)
#     sub_topic = clean_text(sub_match.group(1)) if sub_match else 'Lokale voorzieningen'
    
#     # Location: search for Vught in context
#     loc_match = re.search(r'Vught', main_html)
#     location = 'Vught' if loc_match else 'Unknown Location'
    
#     # WPID from URL
#     wpid_match = re.search(r'wpid=(\d+)', main_url)
#     wpid = wpid_match.group(1) if wpid_match else '2093'
    
#     print(f'Extracted metadata: Main Topic="{main_topic}", Sub Topic="{sub_topic}", Location="{location}", WPID="{wpid}"')
    
#     detail_links = []
#     # Extract detail links from ResultaatTitel divs
#     detail_pattern = r'<div\s+class=[\'"]ResultaatTitel[\'"]>\s*<a\s+href="([^"]+)"[^>]*>.*?</a>\s*</div>'
#     matches = re.findall(detail_pattern, main_html, re.IGNORECASE | re.DOTALL)
#     for href in matches:
#         if '/organisatie/' in href:
#             full_href = normalize_url(href)
#             if full_href not in detail_links:
#                 detail_links.append(full_href)
    
#     print(f'Extracted {len(detail_links)} detail links from main page.')
    
#     print(f'Processing {len(detail_links)} detail links under sub-topic: {sub_topic}')

#     all_entries = []  # Optional: Collect for summary if needed

#     processed_links = detail_links
#     for detail_url in processed_links:
#         # Ensure domain restriction
#         if not urlparse(detail_url).netloc.endswith('voorzieningen.nl'):
#             print(f'  Skipping non-domain link: {detail_url}')
#             continue

#         print(f'  Processing detail: {detail_url}')
#         time.sleep(1)  # Rate limiting

#         detail_html = fetch_page(detail_url)
#         if not detail_html:
#             continue

#         details = extract_details(detail_html)
#         if details['persons'] or details['heading']:
#             print(f'    Details found for {main_topic} > {sub_topic}: {details.get("heading", "N/A")}')
#             append_to_md_file(main_topic, sub_topic, location, wpid, detail_url, details)
#             all_entries.extend(details['persons'])
#         else:
#             print(f'    No details extracted from {detail_url}')

#     print(f'\nScraping completed. Structured data saved to ./scraped_data/all_scraped_data.md')
#     print(f'Total contacts extracted: {len(all_entries)}')

# if __name__ == '__main__':
#     scrape_site()

import subprocess
import json
import os
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
import time

BASE_URL = 'https://voorzieningen.nl'

VUGHT_ORG_FILTER = 'leergeld-vught'  # Retained for URL check logic, but not hardcoded in JSON

def normalize_url(href):
    if href.startswith('http'):
        return href
    return urljoin(BASE_URL, href)

def fetch_page(url):
    try:
        cmd = ['curl', '-s', '-A', 'Mozilla/5.0 (compatible; Scraper)', url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        result.check_returncode()
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"Error fetching {url}: {error}")
        return None

def clean_text(text):
    return re.sub(r'<.*?>', '', text).strip()

def extract_details(html):
    details = {
        'heading': '',
        'description': '',
        'visiting_address': '',
        'persons': [],
        'other_info': {},
        'full_page_text': ''  # New field for all context
    }

    # Extract full page text for comprehensive context
    # Target main content area; fallback to full cleaned HTML
    main_content_match = re.search(r'<div id="dbsContent"[^>]*>(.*?)</div>', html, re.IGNORECASE | re.DOTALL)
    if main_content_match:
        details['full_page_text'] = clean_text(main_content_match.group(1))
    else:
        details['full_page_text'] = clean_text(html)

    # Heading from <h1>
    heading_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
    details['heading'] = heading_match.group(1).strip() if heading_match else ''

    # Description: Doel and Toelichting
    doel_match = re.search(r'<h3>Doel</h3>\s*<p>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
    doel = clean_text(doel_match.group(1)) if doel_match else ''
    toel_match = re.search(r'<h3>Toelichting</h3>\s*<p>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
    toel = clean_text(toel_match.group(1)) if toel_match else ''
    details['description'] = f"Doel: {doel}\nToelichting: {toel}"

    # Other info: Doelstelling
    doelstelling_match = re.search(r'Doelstelling of kernactiviteit:</p>\s*<p>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
    if doelstelling_match:
        details['other_info']['doelstelling'] = clean_text(doelstelling_match.group(1))

    # Contact person details
    persons = []
    name_match = re.search(r'<h3>Contactpersoon</h3>\s*<p>Naam:\s*([^<]+?)(?=<br>|<p|$)', html, re.IGNORECASE | re.DOTALL)
    name = name_match.group(1).strip() if name_match else ''

    phone_matches = re.findall(r'Telefoonnummer:\s*<a\s+href="tel:([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
    phone = ', '.join([match[1].strip() for match in phone_matches]) if phone_matches else ''

    email_matches = re.findall(r'E-mail:\s*<a\s+href="mailto:([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
    email = ', '.join([match[1].strip() for match in email_matches]) if email_matches else ''

    if name and (phone or email):
        persons.append({
            'name': name,
            'phone': phone,
            'email': email
        })

    # Addresses
    # Adres (visiting)
    address_match = re.search(r'<p><b>Adres:</b>?\s*<br ?/?>\s*([^<]+?)(?:<br ?/?><span[^>]*>([^<]+?)</span>)?</p>', html, re.IGNORECASE | re.DOTALL)
    if address_match:
        street = address_match.group(1).strip()
        city_post = address_match.group(2).strip() if address_match.group(2) else ''
        details['visiting_address'] = f"{street}, {city_post}" if city_post else street

    # Bezoekadres alternative
    if not details['visiting_address']:
        bezoek_match = re.search(r'<p>Bezoekadres:</p>\s*<p>([^<]+)</p>\s*<p>([^<]+)</p>', html, re.IGNORECASE | re.DOTALL)
        if bezoek_match:
            details['visiting_address'] = f"{bezoek_match.group(1).strip()}, {bezoek_match.group(2).strip()}"

    # Postal Address
    postal_match = re.search(r'<p><b>Postadres:</b>?\s*<br ?/?>\s*([^<]+?)(?:<br ?/?><span[^>]*>([^<]+?)</span>)?</p>', html, re.IGNORECASE | re.DOTALL)
    postal_address = ''
    if postal_match:
        street = postal_match.group(1).strip()
        city_post = postal_match.group(2).strip() if postal_match.group(2) else ''
        postal_address = f"{street}, {city_post}" if city_post else street
    else:
        # Alternative for Postadres
        post_alt_match = re.search(r'<p>Postadres:</p>\s*<p>([^<]+)</p>\s*<p>([^<]+)</p>', html, re.IGNORECASE | re.DOTALL)
        if post_alt_match:
            postal_address = f"{post_alt_match.group(1).strip()}, {post_alt_match.group(2).strip()}"

    if postal_address:
        for person in persons:
            person['postal_address'] = postal_address
        if not persons:
            # Add to org if no person
            persons.append({'postal_address': postal_address})

    # Website
    website_match = re.search(r'Website:\s*<a\s+href="([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
    website = website_match.group(1).strip() if website_match else ''
    if website:
        for person in persons:
            person['website'] = website
        if not persons:
            persons.append({'website': website})

    # Fallback: Organizational details if no person
    if not persons:
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        org_name = details['heading'] or (title_match.group(1).split(' - ')[0].strip() if title_match else 'Unknown Organization')

        org_phone_matches = re.findall(r'<p[^>]*>Telefoonnummer:\s*([^\s<]+(?:\s-[^\s<]+)?)</p>', html, re.IGNORECASE)
        org_phone = ', '.join([p.strip() for p in org_phone_matches]) if org_phone_matches else ''

        org_email_match = re.search(r'E-mailadres:\s*<a\s+href="mailto:([^"]+)"[^>]*>([^<]+?)</a>', html, re.IGNORECASE | re.DOTALL)
        org_email = org_email_match.group(1).strip() if org_email_match else ''

        persons.append({
            'name': org_name,
            'phone': org_phone,
            'email': org_email,
            'address': details['visiting_address'],
            'postal_address': postal_address,
            'website': website
        })

    details['persons'] = persons

    return details

def append_to_md_file(main_topic, sub_topic, location, wpid, detail_url, details):
    folder_path = os.path.join(os.getcwd(), 'scraped_data')
    os.makedirs(folder_path, exist_ok=True)
    filename = os.path.join(folder_path, 'all_scraped_data.md')

    # Slug for reference
    slug = os.path.basename(detail_url).replace('.html', '')

    # Format as Markdown section
    md_content = f"""

# {main_topic}

## Subtopic: {sub_topic}

### Detail: {slug}

| Field          | Value                  |
|----------------|------------------------|
| Name           | {details.get('persons', [{}])[0].get('name', 'N/A')} |
| Phone          | {details.get('persons', [{}])[0].get('phone', 'N/A')} |
| Email          | {details.get('persons', [{}])[0].get('email', 'N/A')} |
| Visiting Address | {details.get('visiting_address', 'N/A')} |
| Postal Address | {details.get('persons', [{}])[0].get('postal_address', 'N/A')} |
| Website        | {details.get('persons', [{}])[0].get('website', 'N/A')} |

**Heading:** {details.get('heading', 'N/A')}

**Description:** {details.get('description', 'N/A')}

**Other Info:** {details.get('other_info', {})}

**Full Page Text (All Context):** {details.get('full_page_text', 'N/A')}

**Full Data:**\n```json\n{json.dumps(details, indent=2, ensure_ascii=False)}\n```

**Source URL:** {detail_url}

---

*Scraped on: {datetime.now().isoformat()}*"""

    # Check if file exists; if not, add initial header
    if not os.path.exists(filename):
        header = f"# Scraped Data for {main_topic} - Filtered to {location} Municipality (wpid={wpid})\n\n"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(header + md_content)
    else:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(md_content)

    print(f"    Appended structured entry for {slug} to: {filename}")

def scrape_site():
    print('Starting scrape of main page...')
    
    main_url = f'{BASE_URL}/bewegen/aanbod.html?wpid=2093'
    main_html = fetch_page(main_url)
    if not main_html:
        print('Failed to fetch main page. Exiting.')
        return
    
    print(f'Fetched main page successfully.')
    
    # Extract dynamic metadata from main_html and main_url
    # Main topic from title
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', main_html, re.IGNORECASE)
    main_topic = clean_text(title_match.group(1)) if title_match else 'Bewegen & Ontmoeten'
    
    # Sub topic from <B>Lokale voorzieningen (XXX)</B>
    sub_match = re.search(r'<B>([^<]+?)\s*\(\d+\)</B>', main_html, re.IGNORECASE)
    sub_topic = clean_text(sub_match.group(1)) if sub_match else 'Lokale voorzieningen'
    
    # Location: search for Vught in context
    loc_match = re.search(r'Vught', main_html)
    location = 'Vught' if loc_match else 'Unknown Location'
    
    # WPID from URL
    wpid_match = re.search(r'wpid=(\d+)', main_url)
    wpid = wpid_match.group(1) if wpid_match else '2093'
    
    print(f'Extracted metadata: Main Topic="{main_topic}", Sub Topic="{sub_topic}", Location="{location}", WPID="{wpid}"')
    
    detail_links = []
    # Extract detail links from ResultaatTitel divs
    detail_pattern = r'<div\s+class=[\'"]ResultaatTitel[\'"]>\s*<a\s+href="([^"]+)"[^>]*>.*?</a>\s*</div>'
    matches = re.findall(detail_pattern, main_html, re.IGNORECASE | re.DOTALL)
    for href in matches:
        if '/organisatie/' in href:
            full_href = normalize_url(href)
            if full_href not in detail_links:
                detail_links.append(full_href)
    
    print(f'Extracted {len(detail_links)} detail links from main page.')
    
    print(f'Processing {len(detail_links)} detail links under sub-topic: {sub_topic}')

    all_entries = []  # Optional: Collect for summary if needed

    processed_links = detail_links
    for detail_url in processed_links:
        # Ensure domain restriction
        if not urlparse(detail_url).netloc.endswith('voorzieningen.nl'):
            print(f'  Skipping non-domain link: {detail_url}')
            continue

        print(f'  Processing detail: {detail_url}')
        time.sleep(1)  # Rate limiting

        detail_html = fetch_page(detail_url)
        if not detail_html:
            continue

        details = extract_details(detail_html)
        if details['persons'] or details['heading']:
            print(f'    Details found for {main_topic} > {sub_topic}: {details.get("heading", "N/A")}')
            append_to_md_file(main_topic, sub_topic, location, wpid, detail_url, details)
            all_entries.extend(details['persons'])
        else:
            print(f'    No details extracted from {detail_url}')

    print(f'\nScraping completed. Structured data saved to ./scraped_data/all_scraped_data.md')
    print(f'Total contacts extracted: {len(all_entries)}')

if __name__ == '__main__':
    scrape_site()