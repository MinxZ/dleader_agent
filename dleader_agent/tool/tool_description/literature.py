description = [
    {
        "description": "Fetches supplementary information for a paper given its DOI "
        "and saves it to a specified directory.",
        "name": "fetch_supplementary_info_from_doi",
        "optional_parameters": [
            {
                "default": "supplementary_info",
                "description": "Directory to save supplementary files",
                "name": "output_dir",
                "type": "str",
            }
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "The paper DOI",
                "name": "doi",
                "type": "str",
            }
        ],
    },
    {
        "description": "Query arXiv for papers based on the provided search query.",
        "name": "query_arxiv",
        "optional_parameters": [
            {
                "default": 10,
                "description": "The maximum number of papers to retrieve.",
                "name": "max_papers",
                "type": "int",
            }
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "The search query string.",
                "name": "query",
                "type": "str",
            }
        ],
    },
    # DISABLED: Google Scholar tool is not being used
    # {
    #     "description": "Query Google Scholar for papers based on the provided search "
    #     "query and return the first search result.",
    #     "name": "query_scholar",
    #     "optional_parameters": [],
    #     "required_parameters": [
    #         {
    #             "default": None,
    #             "description": "The search query string.",
    #             "name": "query",
    #             "type": "str",
    #         }
    #     ],
    # },
    {
        "description": "Query PubMed for papers based on the provided search query.",
        "name": "query_pubmed",
        "optional_parameters": [
            {
                "default": 10,
                "description": "The maximum number of papers to retrieve.",
                "name": "max_papers",
                "type": "int",
            },
            {
                "default": 3,
                "description": "Maximum number of retry attempts with modified queries.",
                "name": "max_retries",
                "type": "int",
            },
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "The search query string.",
                "name": "query",
                "type": "str",
            }
        ],
    },
    {
        "description": "Search using Google search and return formatted results.",
        "name": "search_google",
        "optional_parameters": [
            {
                "default": 3,
                "description": "Number of results to return",
                "name": "num_results",
                "type": "int",
            },
            {
                "default": "en",
                "description": "Language code for search results",
                "name": "language",
                "type": "str",
            },
        ],
        "required_parameters": [
            {
                "default": None,
                "description": 'The search query (e.g., "protocol text or search question")',
                "name": "query",
                "type": "str",
            }
        ],
    },
    {
        "description": "Extract the text content of a webpage using requests and BeautifulSoup.",
        "name": "extract_url_content",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Webpage URL to extract content from",
                "name": "url",
                "type": "str",
            }
        ],
    },
    {
        "description": "Extract text content from a PDF file.",
        "name": "extract_pdf_content",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "URL of the PDF file",
                "name": "url",
                "type": "str",
            }
        ],
    },
    {
        "description": "Extract the text content of a patent HTML file using Trafilatura with maximum information preservation.",
        "name": "extract_patent_html",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Path to local HTML file to extract content from",
                "name": "html_file_path",
                "type": "str",
            }
        ],
    },

    {
        "description": "Answer questions about images using vision-language models.",
        "name": "image_QA",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "URL of the image to analyze",
                "name": "image_url",
                "type": "str",
            },
            {
                "default": None,
                "description": "Question to ask about the image",
                "name": "question",
                "type": "str",
            }
        ],
    },
    {
        "description": "Extract all patent image URLs from HTML content and save to JSON file.",
        "name": "extract_patent_image_from_urls",
        "optional_parameters": [
            {
                "default": "patent_images.json",
                "description": "Path to save the JSON file containing extracted URLs",
                "name": "output_file",
                "type": "str",
            }
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "HTML content as string to extract patent image URLs from",
                "name": "html_content",
                "type": "str",
            }
        ],
    },

    {
        "description": "Extract entities and structured information from text using Qwen-Max LLM with custom examples. Requires user to provide examples for few-shot learning. Returns JSON with extracted entities grouped by type with attributes.",
        "name": "extract_entities_with_qwen_max",
        "optional_parameters": [
            {
                "default": None,
                "description": "Custom description of extraction task. Example: 'Extract genes, proteins and diseases from biotech patent text'",
                "name": "description",
                "type": "str",
            }
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "Text to extract information from",
                "name": "text",
                "type": "str",
            },
            {
                "default": None,
                "description": "List of entity types to extract. Examples: ['Gene', 'Protein', 'Disease'], ['Patent Number', 'Inventor']",
                "name": "extraction_types",
                "type": "list",
            },
            {
                "default": None,
                "description": "List of example dicts for few-shot learning (REQUIRED). Format: [{'text': 'example text', 'extractions': [{'class': 'Gene', 'text': 'BRCA1', 'attributes': {'function': 'tumor suppressor'}}]}]",
                "name": "examples",
                "type": "list",
            }
        ],
    }
]
