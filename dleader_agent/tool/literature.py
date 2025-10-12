import os
import re
import time
from io import BytesIO
from typing import Optional
from urllib.parse import urljoin

import PyPDF2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googlesearch import search
from openai import OpenAI


def fetch_supplementary_info_from_doi(doi: str, output_dir: str = "supplementary_info"):
    """Fetches supplementary information for a paper given its DOI and returns a research log.

    Args:
        doi: The paper DOI.
        output_dir: Directory to save supplementary files.

    Returns:
        dict: A dictionary containing a research log and the downloaded file paths.

    """
    research_log = []
    research_log.append(f"Starting process for DOI: {doi}")

    # CrossRef API to resolve DOI to a publisher page
    crossref_url = f"https://doi.org/{doi}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(crossref_url, headers=headers)

    if response.status_code != 200:
        log_message = f"Failed to resolve DOI: {doi}. Status Code: {response.status_code}"
        research_log.append(log_message)
        return {"log": research_log, "files": []}

    publisher_url = response.url
    research_log.append(f"Resolved DOI to publisher page: {publisher_url}")

    # Fetch publisher page
    response = requests.get(publisher_url, headers=headers)
    if response.status_code != 200:
        log_message = f"Failed to access publisher page for DOI {doi}."
        research_log.append(log_message)
        return {"log": research_log, "files": []}

    # Parse page content
    soup = BeautifulSoup(response.content, "html.parser")
    supplementary_links = []

    # Look for supplementary materials by keywords or links
    for link in soup.find_all("a", href=True):
        href = link.get("href")
        text = link.get_text().lower()
        if "supplementary" in text or "supplemental" in text or "appendix" in text:
            full_url = urljoin(publisher_url, href)
            supplementary_links.append(full_url)
            research_log.append(
                f"Found supplementary material link: {full_url}")

    if not supplementary_links:
        log_message = f"No supplementary materials found for DOI {doi}."
        research_log.append(log_message)
        return research_log

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    research_log.append(f"Created output directory: {output_dir}")

    # Download supplementary materials
    downloaded_files = []
    for link in supplementary_links:
        file_name = os.path.join(output_dir, link.split("/")[-1])
        file_response = requests.get(link, headers=headers)
        if file_response.status_code == 200:
            with open(file_name, "wb") as f:
                f.write(file_response.content)
            downloaded_files.append(file_name)
            research_log.append(f"Downloaded file: {file_name}")
        else:
            research_log.append(f"Failed to download file from {link}")

    if downloaded_files:
        research_log.append(
            f"Successfully downloaded {len(downloaded_files)} file(s).")
    else:
        research_log.append(f"No files could be downloaded for DOI {doi}.")

    return "\n".join(research_log)


def query_arxiv(query: str, max_papers: int = 10) -> str:
    """Query arXiv for papers based on the provided search query.

    Parameters
    ----------
    - query (str): The search query string.
    - max_papers (int): The maximum number of papers to retrieve (default: 10).

    Returns
    -------
    - str: The formatted search results or an error message.

    """
    import arxiv

    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query, max_results=max_papers, sort_by=arxiv.SortCriterion.Relevance)
        results = "\n\n".join(
            [f"Title: {paper.title}\nSummary: {paper.summary}" for paper in client.results(search)])
        return results if results else "No papers found on arXiv."
    except Exception as e:
        return f"Error querying arXiv: {e}"


def query_scholar(query: str) -> str:
    """Query Google Scholar for papers based on the provided search query.

    Parameters
    ----------
    - query (str): The search query string.

    Returns
    -------
    - str: The first search result formatted or an error message.

    """
    from scholarly import scholarly

    try:
        search_query = scholarly.search_pubs(query)
        result = next(search_query, None)
        if result:
            return f"Title: {result['bib']['title']}\nYear: {result['bib']['pub_year']}\nVenue: {result['bib']['venue']}\nAbstract: {result['bib']['abstract']}"
        else:
            return "No results found on Google Scholar."
    except Exception as e:
        return f"Error querying Google Scholar: {e}"


def query_pubmed(query: str, max_papers: int = 10, max_retries: int = 3) -> str:
    """Query PubMed for papers based on the provided search query.

    Parameters
    ----------
    - query (str): The search query string.
    - max_papers (int): The maximum number of papers to retrieve (default: 10).
    - max_retries (int): Maximum number of retry attempts with modified queries (default: 3).

    Returns
    -------
    - str: The formatted search results or an error message.

    """
    from pymed import PubMed

    try:
        # Update with a valid email address
        pubmed = PubMed(tool="MyTool", email="your-email@example.com")

        # Initial attempt
        papers = list(pubmed.query(query, max_results=max_papers))

        # Retry with modified queries if no results
        retries = 0
        while not papers and retries < max_retries:
            retries += 1
            # Simplify query with each retry by removing the last word
            simplified_query = " ".join(
                query.split()[:-retries]) if len(query.split()) > retries else query
            time.sleep(1)  # Add delay between requests
            papers = list(pubmed.query(
                simplified_query, max_results=max_papers))

        if papers:
            results = "\n\n".join(
                [f"Title: {paper.title}\nAbstract: {paper.abstract}\nJournal: {paper.journal}" for paper in papers]
            )
            return results
        else:
            return "No papers found on PubMed after multiple query attempts."
    except Exception as e:
        return f"Error querying PubMed: {e}"


def search_google(query: str, num_results: int = 3, language: str = "en") -> list[dict]:
    """Search using Google search.

    Args:
        query (str): The search query (e.g., "protocol text or seach question")
        num_results (int): Number of results to return (default: 10)
        language (str): Language code for search results (default: 'en')
        pause (float): Pause between searches to avoid rate limiting (default: 2.0 seconds)

    Returns:
        List[dict]: List of dictionaries containing search results with title and URL

    """
    try:
        results_string = ""
        search_query = f"{query}"

        for res in search(search_query, num_results=num_results, lang=language, advanced=True):
            title = res.title
            url = res.url
            description = res.description

            results_string += f"Title: {title}\nURL: {url}\nDescription: {description}\n\n"

    except Exception as e:
        print(f"Error performing search: {str(e)}")
    return results_string


def extract_url_content(url: str) -> str:
    """Extract the text content of a webpage using requests and BeautifulSoup.

    Args:
        url: Webpage URL to extract content from

    Returns:
        Text content of the webpage

    """
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

    # Check if the response is in text format
    if "text/plain" in response.headers.get("Content-Type", "") or "application/json" in response.headers.get(
        "Content-Type", ""
    ):
        return response.text.strip()  # Return plain text or JSON response directly

    # If it's HTML, use BeautifulSoup to parse
    soup = BeautifulSoup(response.text, "html.parser")

    # Try to find main content first, fallback to body
    content = soup.find("main") or soup.find("article") or soup.body

    # Remove unwanted elements
    for element in content(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
        element.decompose()

    # Extract text with better formatting
    paragraphs = content.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
    cleaned_text = []

    for p in paragraphs:
        text = p.get_text().strip()
        if text:  # Only add non-empty paragraphs
            cleaned_text.append(text)

    return "\n\n".join(cleaned_text)


def extract_pdf_content(url: str) -> str:
    """Extract the text content of a PDF file given its URL.

    Args:
        url: URL of the PDF file to extract text from

    Returns:
        The extracted text content from the PDF

    """
    try:
        # Check if the URL ends with .pdf
        if not url.lower().endswith(".pdf"):
            # If not, try to find a PDF link on the page
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                # Look for PDF links in the HTML content
                pdf_links = re.findall(
                    r'href=[\'"]([^\'"]+\.pdf)[\'"]', response.text)
                if pdf_links:
                    # Use the first PDF link found
                    if not pdf_links[0].startswith("http"):
                        # Handle relative URLs
                        base_url = "/".join(url.split("/")[:3])
                        url = base_url + \
                            pdf_links[0] if pdf_links[0].startswith(
                                "/") else base_url + "/" + pdf_links[0]
                    else:
                        url = pdf_links[0]
                else:
                    return f"No PDF file found at {url}. Please provide a direct link to a PDF file."

        # Download the PDF
        response = requests.get(url, timeout=30)

        # Check if we actually got a PDF file (by checking content type or magic bytes)
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/pdf" not in content_type and not response.content.startswith(b"%PDF"):
            return f"The URL did not return a valid PDF file. Content type: {content_type}"

        pdf_file = BytesIO(response.content)

        # Try with PyPDF2 first
        try:
            text = ""
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n\n"
        except Exception as e:
            print(f"Error extracting text from PDF: {str(e)}")

        # Clean up the text
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            return "The PDF file did not contain any extractable text. It may be an image-based PDF requiring OCR."

        return text

    except requests.exceptions.RequestException as e:
        return f"Error downloading PDF: {str(e)}"
    except Exception as e:
        return f"Error extracting text from PDF: {str(e)}"


def extract_patent_html(html_file_path: str) -> str:
    """Extract the text content of a patent HTML file using Trafilatura.

    Args:
        html_file_path: Path to local HTML file to extract content from

    Returns:
        Text content of the patent document with maximum information preservation

    """
    try:
        import trafilatura
    except ImportError:
        raise ImportError(
            "trafilatura not installed. Run: pip install trafilatura")

    with open(html_file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    result = trafilatura.extract(html_content,
                                 include_comments=True,
                                 include_tables=True,
                                 include_links=True
                                 )

    return result.strip() if result else ""


def extract_patent_image_from_urls(html_content: str, output_file: str = "patent_images.json") -> list:
    """Extract all patent image URLs from HTML content and save to JSON.

    Args:
        html_content: HTML content as string
        output_file: Path to save the JSON file (default: "patent_images.json")

    Returns:
        List of URLs that start with https://patentimages.storage.googleapis.com and end with .png
    """
    import json
    import re

    # Extract URLs using regex pattern
    url_pattern = r'https://patentimages\.storage\.googleapis\.com[^\s"\'<>]*\.png'
    all_matches = re.findall(url_pattern, html_content)
    
    # Remove duplicates and sort
    filtered_urls = sorted(list(set(all_matches)))

    # Save to JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(filtered_urls, f, indent=2, ensure_ascii=False)

    return filtered_urls
    

def image_QA(image_url: str, question: str) -> str:
    """Extract answers from patent images using vision-language models.

    Args:
        image_url: URL of the patent image to analyze
        question: Question to ask about the image

    Returns:
        Answer text from the model
    """
    try:
        # Load API key from .env file
        load_dotenv()
        api_key = os.getenv("QWEN_API")

        if not api_key:
            return "Error: QWEN_API key not found in .env file. Please check your configuration."

        # Validate image URL
        if not image_url.startswith(("http://", "https://")):
            return f"Error: Invalid image URL. Must start with http:// or https://. Got: {image_url}"

        # Initialize OpenAI client
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )

        # Call the model
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://localhost",
                "X-Title": "Patent Image Q&A"
            },
            model="qwen/qwen3-vl-235b-a22b-thinking",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        }
                    ]
                }
            ],
            temperature=0.1
        )

        # Extract and return the answer
        answer = completion.choices[0].message.content
        return answer.strip()

    except Exception as e:
        return f"Error processing image Q&A: {str(e)}"


def extract_entities_with_qwen_max(
    text: str,
    extraction_types: list[str],
    description: str = None,
    examples: list[dict] = None
) -> dict:
    """Extract entities and structured information from text using Qwen-Max LLM.

    Args:
        text: The text to extract information from
        extraction_types: List of entity types to extract (e.g., ["Gene", "Protein", "Disease"])
        description: Optional description of what to extract. If None, auto-generates based on extraction_types
        examples: List of example dicts. Format:
                  [{"text": "example text", "extractions": [{"class": "Gene", "text": "BRCA1", "attributes": {...}}]}]

    Returns:
        Dictionary with extraction results grouped by type
    """
    import logging
    import os
    from collections import defaultdict

    import langextract as lx
    from dotenv import load_dotenv
    from langextract.providers.openai import OpenAILanguageModel

    try:
        # Load API key
        load_dotenv()
        api_key = os.getenv("QWEN_API")

        if not api_key:
            return {"error": "QWEN_API key not found in .env file", "success": False}

        # Validate inputs
        if not text or not text.strip():
            return {"error": "Text cannot be empty", "success": False}

        if not extraction_types or len(extraction_types) == 0:
            return {"error": "extraction_types cannot be empty", "success": False}

        if not examples or len(examples) == 0:
            return {"error": "examples cannot be empty. Please provide at least one example.", "success": False}

        # Auto-generate description if not provided
        if description is None:
            types_str = ", ".join(extraction_types)
            description = f"Extract {types_str} from the text. Use exact text from the original and provide meaningful attributes."

        # Parse custom examples
        parsed_examples = []
        for example in examples:
            if "text" not in example or "extractions" not in example:
                continue
            extractions = []
            for ext in example["extractions"]:
                if "class" not in ext or "text" not in ext:
                    continue
                extractions.append(
                    lx.data.Extraction(
                        extraction_class=ext["class"],
                        extraction_text=ext["text"],
                        attributes=ext.get("attributes", {})
                    )
                )
            parsed_examples.append(
                lx.data.ExampleData(
                    text=example["text"], extractions=extractions)
            )

        if len(parsed_examples) == 0:
            return {"error": "No valid examples provided. Check example format.", "success": False}

        # Configure model with Qwen-Max
        model = OpenAILanguageModel(
            model_id='qwen/qwen3-max',
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        # Suppress warnings
        logging.getLogger('absl').setLevel(logging.ERROR)

        # Extract
        result = lx.extract(
            text_or_documents=text,
            prompt_description=description,
            examples=parsed_examples,
            model=model,
            fence_output=True,
            use_schema_constraints=False,
            align_extractions=False
        )

        # Format results
        grouped = defaultdict(list)
        for extraction in result.extractions:
            grouped[extraction.extraction_class].append({
                "text": extraction.extraction_text,
                "attributes": extraction.attributes if extraction.attributes else {}
            })

        # Convert to regular dict and add summary
        output = dict(grouped)
        output["summary"] = {
            "total_entities": len(result.extractions),
            "types_found": list(grouped.keys())
        }
        output["success"] = True

        return output

    except Exception as e:
        return {"error": f"Error during extraction: {str(e)}", "success": False}
