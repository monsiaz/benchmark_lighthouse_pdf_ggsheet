import requests
import subprocess
import json
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
import io
import datetime
import gspread
from google.oauth2.service_account import Credentials
from concurrent.futures import ThreadPoolExecutor, as_completed

# Path to the service account JSON file
credentials_path = 'service_account.json'

# Google Sheets setup
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(credentials_path, scopes=scope)
client = gspread.authorize(creds)

# URLs organized by site and page type
urls = {
    "Infonet": {
        "Dirigeants": [
            "https://infonet.fr/dirigeants/66aa12375da7ac2c4b9ea075/",
            "https://infonet.fr/dirigeants/66aa63225da7ac2c4b5bbb87/",
            "https://infonet.fr/dirigeants/66a9ce718032d296dfc1f09b/",
            "https://infonet.fr/dirigeants/66a9e10a41b8769963336c37/"
        ],
        "Entreprises": [
            "https://infonet.fr/entreprises/49215593200048-winamax/",
            "https://infonet.fr/entreprises/83289588200013-good-light/",
            "https://infonet.fr/entreprises/79940307600018-avril-gestion/",
            "https://infonet.fr/entreprises/55210793000026-hotel-de-sers/"
        ]
    },
    "Pappers": {
        "Dirigeants": [
            "https://www.pappers.fr/dirigeant/christophe_schaming_1968-12",
            "https://www.pappers.fr/dirigeant/laurie_laborde_1977-12",
            "https://www.pappers.fr/dirigeant/antoine_henrion_1962-04",
            "https://www.pappers.fr/dirigeant/anne_besse_1959-04"
        ],
        "Entreprises": [
            "https://www.pappers.fr/entreprise/winamax-492155932",
            "https://www.pappers.fr/entreprise/good-light-832895882",
            "https://www.pappers.fr/entreprise/avril-gestion-799403076",
            "https://www.pappers.fr/entreprise/hotel-de-sers-552107930"
        ]
    },
    "Société.com": {
        "Dirigeants": [
            "https://dirigeant.societe.com/dirigeant/Christophe.SCHAMING.52286470.html",
            "https://dirigeant.societe.com/dirigeant/Laurie.LABORDE.71267822.html",
            "https://dirigeant.societe.com/dirigeant/Antoine.HENRION.16870522.html",
            "https://dirigeant.societe.com/dirigeant/Anne.JOUSSE.19262605.html"
        ],
        "Entreprises": [
            "https://www.societe.com/societe/winamax-492155932.html",
            "https://www.societe.com/societe/good-light-832895882.html",
            "https://www.societe.com/societe/avril-gestion-799403076.html",
            "https://www.societe.com/societe/hotel-de-sers-552107930.html"
        ]
    }
}

# Function to run Lighthouse tests
def run_lighthouse_test(url):
    try:
        result = subprocess.run(['node', 'lighthouse_test.mjs', url], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"Error testing URL {url}: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        print(f"Timeout expired for URL {url}")
        return None

# Function to extract metrics and calculate averages
def process_urls(urls):
    metrics = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(run_lighthouse_test, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            result = future.result()
            if result:
                try:
                    # Extract metrics safely, checking if the key exists
                    fcp = result['audits'].get('first-contentful-paint', {}).get('numericValue', 0) / 1000.0
                    si = result['audits'].get('speed-index', {}).get('numericValue', 0) / 1000.0
                    lcp = result['audits'].get('largest-contentful-paint', {}).get('numericValue', 0) / 1000.0
                    tti = result['audits'].get('interactive', {}).get('numericValue', 0) / 1000.0
                    tbt = result['audits'].get('total-blocking-time', {}).get('numericValue', 0) / 1000.0
                    cls = result['audits'].get('cumulative-layout-shift', {}).get('numericValue', 0)

                    # Only add metrics if they are valid
                    metrics.append({
                        "url": url,
                        "FCP": fcp,
                        "SI": si,
                        "LCP": lcp,
                        "TTI": tti,
                        "TBT": tbt,
                        "CLS": cls
                    })
                    print(f"Metrics collected for: {url}")
                except Exception as e:
                    print(f"Error parsing data for URL {url}: {e}")
                    print(f"Full result for debugging: {json.dumps(result, indent=2)}")
            else:
                print(f"Failed to get metrics for: {url}")
    return metrics

# Generate comparison graph
def generate_comparison_graph(data, page_type):
    print(f"Generating comparison graph for: {page_type}")
    metrics = ["FCP", "SI", "LCP", "TTI", "TBT", "CLS"]
    width = 0.2
    x = range(len(metrics))
    fig, ax = plt.subplots(figsize=(10, 6))

    for i, site in enumerate(data):
        values = [site["averages"].get(metric, 0) for metric in metrics]
        ax.bar([p + width * i for p in x], values, width=width, label=site["site_name"])

    ax.set_xlabel("Metric")
    ax.set_ylabel("Time (s)")
    ax.set_xticks([p + width * (len(data) - 1) / 2 for p in x])
    ax.set_xticklabels(metrics)
    ax.legend(loc="best")
    ax.set_title(f"Average Metrics Comparison for {page_type}")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    print(f"Graph generated for: {page_type}")
    return buf

# Function to generate PDF report with separate graphs and tables
def generate_pdf_report(results, output_file, sheet_data):
    print(f"Generating PDF report: {output_file}")
    doc = SimpleDocTemplate(output_file, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()
    title_style = styles['Title']  # Consistent style for titles
    
    # Separate data for each page type
    entreprises_data = [row for row in sheet_data if row[2] == "Entreprises"]
    dirigeants_data = [row for row in sheet_data if row[2] == "Dirigeants"]

    # Page 1: Graph and Table for Entreprises
    elements.append(Paragraph("Performance Report: Entreprises", title_style))
    elements.append(Spacer(1, 8))
    comparison_graph_entreprises = generate_comparison_graph(results["Entreprises"], "Entreprises")
    elements.append(Image(comparison_graph_entreprises, width=400, height=250))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Performance Metrics Summary - Entreprises", styles['Heading2']))
    table_data = [["Timestamp", "Site", "Groupe", "Avg FCP", "Avg SI", "Avg LCP", "Avg TTI", "Avg TBT", "Avg CLS"]]
    for row in entreprises_data:
        row[0] = row[0][:10]  # Shorten timestamp for display
        table_data.append(row)
    table = Table(table_data, colWidths=[80, 70, 60, 50, 50, 50, 50, 50, 50])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    elements.append(PageBreak())  # Ensure the next section starts on a new page

    # Page 2: Graph and Table for Dirigeants
    elements.append(Paragraph("Performance Report: Dirigeants", title_style))
    elements.append(Spacer(1, 8))
    comparison_graph_dirigeants = generate_comparison_graph(results["Dirigeants"], "Dirigeants")
    elements.append(Image(comparison_graph_dirigeants, width=400, height=250))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Performance Metrics Summary - Dirigeants", styles['Heading2']))
    table_data = [["Timestamp", "Site", "Groupe", "Avg FCP", "Avg SI", "Avg LCP", "Avg TTI", "Avg TBT", "Avg CLS"]]
    for row in dirigeants_data:
        row[0] = row[0][:10]  # Shorten timestamp for display
        table_data.append(row)
    table = Table(table_data, colWidths=[80, 70, 60, 50, 50, 50, 50, 50, 50])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    elements.append(PageBreak())  # Ensure the next section starts on a new page

    # Page 3: Methodology and Explanation
    elements.append(Paragraph("Methodology", title_style))
    elements.append(Spacer(1, 12))
    methodology_block = """
    <b>Methodology</b><br/>
    We used Lighthouse results to evaluate web page performance.<br/><br/>
    Lighthouse is an open-source automated tool to improve web page quality.<br/><br/>
    It was run on a selection of pages to gather metrics such as First Contentful Paint (FCP), Speed Index (SI), Largest Contentful Paint (LCP), Time to Interactive (TTI), Total Blocking Time (TBT), and Cumulative Layout Shift (CLS).<br/><br/>
    Each metric is assessed based on defined thresholds, and comments are provided to help interpret the results.
    """
    elements.append(Paragraph(methodology_block, styles['BodyText']))
    elements.append(Spacer(1, 12))

    explanation_block = """
    <b>Explanation of Metrics</b><br/>
    <b>First Contentful Paint (FCP)</b>: The time until the first text or image is displayed.<br/><br/>
    <b>Speed Index (SI)</b>: How quickly the content of a page is visually complete.<br/><br/>
    <b>Largest Contentful Paint (LCP)</b>: The render time of the largest visible element in the viewport.<br/><br/>
    <b>Time to Interactive (TTI)</b>: The time until the page is fully interactive.<br/><br/>
    <b>Total Blocking Time (TBT)</b>: The sum of all time between FCP and TTI where the main thread was blocked long enough to prevent responsiveness.<br/><br/>
    <b>Cumulative Layout Shift (CLS)</b>: Measures the total of all unexpected layout shift scores that occur during the entire lifespan of the page.<br/><br/>
    """
    elements.append(Paragraph(explanation_block, styles['BodyText']))

    doc.build(elements)
    print(f"PDF report generated: {output_file}")

# Function to publish results to Google Sheets and return the data
def publish_to_google_sheets(results):
    print("Publishing results to Google Sheets...")
    try:
        summary_sheet = client.open('Sitemap Results').sheet1
    except gspread.SpreadsheetNotFound:
        # Create the spreadsheet if it does not exist
        spreadsheet = client.create('Sitemap Results')
        spreadsheet.share('', perm_type='anyone', role='writer')  # Allow anyone with the link to edit
        summary_sheet = spreadsheet.sheet1
        print("Created new Google Sheet: Sitemap Results")

    headers = ["Timestamp", "Site", "Groupe", "Avg FCP", "Avg SI", "Avg LCP", "Avg TTI", "Avg TBT", "Avg CLS"]
    existing_headers = summary_sheet.row_values(1)
    if not existing_headers:
        summary_sheet.append_row(headers)
    
    timestamp = datetime.datetime.now().isoformat()
    sheet_data = []
    for page_type, sites in results.items():
        for site in sites:
            averages = site["averages"]
            row = [
                timestamp,
                site["site_name"],
                page_type,
                round(averages.get("FCP", 0), 2),
                round(averages.get("SI", 0), 2),
                round(averages.get("LCP", 0), 2),
                round(averages.get("TTI", 0), 2),
                round(averages.get("TBT", 0), 2),
                round(averages.get("CLS", 0), 2)
            ]
            summary_sheet.append_row(row)
            sheet_data.append(row)
    print("Results published to Google Sheets.")
    return sheet_data

# Main execution function
def main():
    print("Starting the performance reporting script...")
    results = {}
    for site_name, page_types in urls.items():
        print(f"Processing site: {site_name}")
        for page_type, page_urls in page_types.items():
            print(f"Processing page type: {page_type}")
            if page_type not in results:
                results[page_type] = []
            metrics = process_urls(page_urls)
            if metrics:
                # Ensure only numerical values are summed
                averages = {}
                for metric in metrics[0].keys():
                    if metric not in ['url']:  # Ensure we're not processing URLs as metrics
                        try:
                            values = [float(d[metric]) for d in metrics if isinstance(d[metric], (int, float, str)) and d[metric] != '']
                            averages[metric] = sum(values) / len(values) if values else 0
                        except ValueError as e:
                            print(f"Skipping metric {metric} due to value error: {e}")
                
                results[page_type].append({"site_name": site_name, "averages": averages})
                print(f"Averages calculated for {page_type} of {site_name}")

    # Publish Results to Google Sheets and get data
    sheet_data = publish_to_google_sheets(results)
    
    # Generate PDF Report with separate graphs for each page type
    generate_pdf_report(results, "performance_report_comparison.pdf", sheet_data)
    print("Script execution completed.")

if __name__ == "__main__":
    main()
