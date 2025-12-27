"""
Sentence Buffer - Accumulates text chunks and yields complete sentences.

This module provides intelligent sentence boundary detection for streaming
text-to-speech applications. It buffers incoming text chunks and yields
complete sentences as soon as they're detected, enabling low-latency TTS
while avoiding awkward mid-sentence pauses.
"""

import re
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class SentenceBuffer:
    """
    Buffer text chunks and yield complete sentences.

    Handles intelligent sentence boundary detection, including:
    - Standard sentence endings: . ! ?
    - Abbreviations: Dr., Mr., Mrs., etc.
    - Minimum sentence length to avoid tiny fragments
    - Proper handling of partial words split across chunks
    """

    # Common abbreviations that don't end sentences
    ABBREVIATIONS = {
        "dr",
        "mr",
        "mrs",
        "ms",
        "prof",
        "sr",
        "jr",
        "etc",
        "vs",
        "e.g",
        "i.e",
        "inc",
        "corp",
        "ltd",
        "ave",
        "blvd",
        "st",
        "rd",
        "apt",
        "no",
        "vol",
    }

    def __init__(self, min_sentence_length: int = 20):
        """
        Initialize sentence buffer.

        Args:
            min_sentence_length: Minimum characters before yielding a sentence
                               (prevents tiny fragments from being sent to TTS)
        """
        self.buffer = ""
        self.min_sentence_length = min_sentence_length

    def add_chunk(self, chunk: str) -> List[str]:
        """
        Add a text chunk and return any complete sentences.

        Args:
            chunk: Text chunk from LLM stream

        Returns:
            List of complete sentences ready for TTS (may be empty)
        """
        self.buffer += chunk
        return self._extract_sentences()

    def flush(self) -> Optional[str]:
        """
        Flush remaining buffer content as final sentence.

        Call this when the stream is complete to get any remaining text.

        Returns:
            Remaining text if any, or None
        """
        if self.buffer.strip():
            content = self.buffer.strip()
            self.buffer = ""
            return content
        return None

    def _extract_sentences(self) -> List[str]:
        """
        Extract complete sentences from buffer.

        Returns:
            List of complete sentences (buffer is updated with remaining text)
        """
        sentences = []

        while True:
            # Find potential sentence ending
            match = self._find_sentence_boundary()

            if match is None:
                # No complete sentence found
                break

            # Extract sentence
            sentence = self.buffer[: match.end()].strip()

            # Update buffer (remove extracted sentence)
            self.buffer = self.buffer[match.end() :].lstrip()

            # Only yield if it meets minimum length
            if len(sentence) >= self.min_sentence_length:
                sentences.append(sentence)
                logger.debug(
                    f"Extracted sentence ({len(sentence)} chars): {sentence[:50]}..."
                )
            else:
                # Too short, put it back in buffer
                logger.debug(
                    f"Sentence too short ({len(sentence)} chars), buffering: {sentence}"
                )
                self.buffer = sentence + " " + self.buffer

        return sentences

    def _find_sentence_boundary(self) -> Optional[re.Match]:
        """
        Find the next sentence boundary in the buffer.

        Handles:
        - Standard endings: . ! ?
        - Abbreviations: Dr., Mr., etc. (not sentence endings)
        - Ensures we have enough text after the period to determine if it's an abbreviation

        Returns:
            Match object for sentence boundary, or None if no complete sentence
        """
        # Look for sentence boundaries: . ! ? followed by space + capital letter
        # This is the most reliable indicator of a sentence boundary
        pattern = r"[.!?](?=\s+[A-Z])"
        matches = list(re.finditer(pattern, self.buffer))

        if matches:
            # Check each match to exclude abbreviations
            for match in matches:  # Check from first to last
                # Get word before the punctuation
                text_before = self.buffer[: match.start()]
                words_before = text_before.split()

                if words_before and match.group() == ".":
                    # Only check for abbreviations with periods
                    last_word = words_before[-1].lower().rstrip(".")

                    # Check if it's a known abbreviation
                    if last_word in self.ABBREVIATIONS:
                        # Skip this match, it's an abbreviation
                        continue

                # This is a valid sentence boundary
                return match

        # Also check for sentence ending at end of buffer (with no following text)
        # Only do this if buffer is substantial and ends with sentence punctuation
        if len(self.buffer) > self.min_sentence_length:
            end_pattern = r"[.!?]\s*$"
            match = re.search(end_pattern, self.buffer)
            if match:
                # Only check abbreviations for periods
                if match.group().strip() == ".":
                    text_before = self.buffer[: match.start()]
                    words_before = text_before.split()

                    if words_before:
                        last_word = words_before[-1].lower().rstrip(".")
                        if last_word in self.ABBREVIATIONS:
                            return None

                return match

        return None

    def reset(self):
        """Reset the buffer, clearing all accumulated text."""
        self.buffer = ""
