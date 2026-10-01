import json
import re
from pathlib import Path
from typing import Dict, Any, List

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

class DocumentParser:
    """
    Parses messy business documents from HTML, JSON, Markdown, and Plaintext formats.
    Extracts semantic sections, titles, and raw body text.
    """

    def parse_file(self, file_path: Path) -> Dict[str, Any]:
        """Route to appropriate parser based on file suffix."""
        suffix = file_path.suffix.lower()
        content = file_path.read_text(encoding="utf-8", errors="replace")

        if suffix in [".html", ".htm"]:
            return self.parse_html(content, file_path.name)
        elif suffix == ".json":
            return self.parse_json(content, file_path.name)
        elif suffix in [".md", ".markdown"]:
            return self.parse_markdown(content, file_path.name)
        else:
            return self.parse_text(content, file_path.name)

    def parse_html(self, content: str, filename: str) -> Dict[str, Any]:
        """Extract structured body content from HTML, discarding scripts and navigation."""
        if BS4_AVAILABLE:
            soup = BeautifulSoup(content, "html.parser")
            # Remove navigation, header, footer, scripts, styles
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()

            title_tag = soup.find("title") or soup.find("h1")
            title = title_tag.get_text(strip=True) if title_tag else filename

            # Extract main content or body
            main_body = soup.find("main") or soup.find("body") or soup
            text = main_body.get_text(separator="\n", strip=True)
        else:
            # Fallback regex-based HTML tag removal
            title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else filename
            # Strip nav, header, footer blocks
            cleaned = re.sub(r'<(?:nav|header|footer)[^>]*>.*?</(?:nav|header|footer)>', '', content, flags=re.DOTALL | re.IGNORECASE)
            # Strip all remaining tags
            text = re.sub(r'<[^>]+>', ' ', cleaned)
            text = re.sub(r'\s+', ' ', text).strip()

        return {
            "title": title,
            "raw_text": text,
            "source": filename,
            "format": "html"
        }

    def parse_json(self, content: str, filename: str) -> Dict[str, Any]:
        """Parse structured JSON underwriting and qualification documents."""
        data = json.loads(content)
        title = data.get("title", filename)
        category = data.get("category", "qualification_rules")
        version = data.get("version", "1.0")

        # Flatten rules list into readable text blocks
        blocks = []
        rules = data.get("rules", [])
        for rule in rules:
            rule_id = rule.get("rule_id", "")
            rule_name = rule.get("name", "")
            guideline = rule.get("guideline", "")
            rationale = rule.get("actuarial_rationale", "")
            block_text = f"Rule {rule_id}: {rule_name}. {guideline}"
            if rationale:
                block_text += f" Actuarial Rationale: {rationale}"
            blocks.append(block_text)

        raw_text = "\n\n".join(blocks) if blocks else json.dumps(data, indent=2)

        return {
            "title": title,
            "raw_text": raw_text,
            "source": filename,
            "format": "json",
            "category": category,
            "version": version,
            "metadata": {"rule_count": len(rules)}
        }

    def parse_markdown(self, content: str, filename: str) -> Dict[str, Any]:
        """Parse markdown documents, extracting title from first h1 header."""
        lines = content.splitlines()
        title = filename
        for line in lines:
            if line.startswith("# "):
                title = line.replace("# ", "").strip()
                break

        return {
            "title": title,
            "raw_text": content,
            "source": filename,
            "format": "markdown"
        }

    def parse_text(self, content: str, filename: str) -> Dict[str, Any]:
        """Parse plaintext documents."""
        first_line = content.splitlines()[0] if content.splitlines() else filename
        title = first_line.strip("[]# \t")[:80]
        return {
            "title": title,
            "raw_text": content,
            "source": filename,
            "format": "text"
        }

parser = DocumentParser()
