"""
Tests for SentenceBuffer - Intelligent sentence boundary detection.
"""

import pytest
from services.sentence_buffer import SentenceBuffer


class TestSentenceBuffer:
    """Test cases for SentenceBuffer class."""

    def test_single_complete_sentence(self):
        """Test extracting a single complete sentence."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("Hello, this is a test sentence.")

        assert len(sentences) == 1
        assert sentences[0] == "Hello, this is a test sentence."
        assert buffer.buffer == ""

    def test_multiple_sentences(self):
        """Test extracting multiple sentences from a single chunk."""
        buffer = SentenceBuffer(min_sentence_length=10)

        # Note: The last sentence won't be extracted until we have text after it
        # or flush the buffer (this is correct behavior for streaming)
        sentences = buffer.add_chunk("First sentence. Second sentence! Third sentence?")

        assert len(sentences) == 2
        assert sentences[0] == "First sentence."
        assert sentences[1] == "Second sentence!"

        # Get the remaining sentence
        remaining = buffer.flush()
        assert remaining == "Third sentence?"

    def test_incremental_chunks(self):
        """Test adding text incrementally across multiple chunks."""
        buffer = SentenceBuffer(min_sentence_length=10)

        # First chunk - no complete sentence yet
        sentences = buffer.add_chunk("This is the beginning")
        assert len(sentences) == 0

        # Second chunk - completes the sentence
        sentences = buffer.add_chunk(" of a sentence.")
        assert len(sentences) == 1
        assert sentences[0] == "This is the beginning of a sentence."

    def test_abbreviation_handling_dr(self):
        """Test that Dr. is not treated as sentence ending."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("I visited Dr. Smith yesterday. He was helpful.")

        # Should be 2 sentences, not 3 (Dr. shouldn't split)
        assert len(sentences) == 2
        assert "Dr. Smith" in sentences[0]
        assert sentences[1] == "He was helpful."

    def test_abbreviation_handling_mr(self):
        """Test that Mr. is not treated as sentence ending."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("Mr. Johnson called today. We talked for an hour.")

        assert len(sentences) == 2
        assert "Mr. Johnson" in sentences[0]

    def test_abbreviation_handling_etc(self):
        """Test that etc. is not treated as sentence ending."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("I like apples, oranges, etc. They are healthy.")

        # Should be 1 complete sentence (the second has no text after it yet)
        assert len(sentences) == 1
        assert "etc." in sentences[0]
        assert "They are healthy" in sentences[0]

    def test_minimum_length_threshold(self):
        """Test that sentences below minimum length are buffered."""
        buffer = SentenceBuffer(min_sentence_length=20)

        # Short sentence - should be buffered
        sentences = buffer.add_chunk("Hi there.")
        assert len(sentences) == 0
        assert "Hi there." in buffer.buffer

        # Add more text to exceed threshold
        sentences = buffer.add_chunk(" How are you doing today?")
        assert len(sentences) == 1
        assert "Hi there. How are you doing today?" in sentences[0]

    def test_flush_remaining_text(self):
        """Test flushing remaining buffer content."""
        buffer = SentenceBuffer(min_sentence_length=10)

        buffer.add_chunk("This is incomplete")

        # Flush should return remaining text
        remaining = buffer.flush()
        assert remaining == "This is incomplete"
        assert buffer.buffer == ""

    def test_flush_empty_buffer(self):
        """Test flushing when buffer is empty."""
        buffer = SentenceBuffer(min_sentence_length=10)

        remaining = buffer.flush()
        assert remaining is None

    def test_exclamation_marks(self):
        """Test sentence detection with exclamation marks."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("This is exciting! I can't believe it!")

        assert len(sentences) == 2
        assert sentences[0] == "This is exciting!"
        assert sentences[1] == "I can't believe it!"

    def test_question_marks(self):
        """Test sentence detection with question marks."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("What is this? How does it work?")

        assert len(sentences) == 2
        assert sentences[0] == "What is this?"
        assert sentences[1] == "How does it work?"

    def test_mixed_punctuation(self):
        """Test sentences with mixed punctuation."""
        buffer = SentenceBuffer(min_sentence_length=10)

        text = "First one. Second one! Third one? Fourth one."
        sentences = buffer.add_chunk(text)

        assert len(sentences) == 4
        assert sentences[0] == "First one."
        assert sentences[1] == "Second one!"
        assert sentences[2] == "Third one?"
        assert sentences[3] == "Fourth one."

    def test_partial_word_split(self):
        """Test handling of partial words split across chunks."""
        buffer = SentenceBuffer(min_sentence_length=10)

        # First chunk ends mid-word
        sentences = buffer.add_chunk("This is a very long sen")
        assert len(sentences) == 0

        # Complete the word and sentence
        sentences = buffer.add_chunk("tence that was split.")
        assert len(sentences) == 1
        assert sentences[0] == "This is a very long sentence that was split."

    def test_multiple_spaces(self):
        """Test handling of multiple spaces between sentences."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("First sentence.    Second sentence.")

        assert len(sentences) == 2
        # Whitespace should be normalized
        assert sentences[0] == "First sentence."
        assert sentences[1] == "Second sentence."

    def test_reset(self):
        """Test resetting the buffer."""
        buffer = SentenceBuffer(min_sentence_length=10)

        buffer.add_chunk("Some incomplete text")
        assert len(buffer.buffer) > 0

        buffer.reset()
        assert buffer.buffer == ""

    def test_long_sentence_exceeds_min_length(self):
        """Test that a long sentence is still extracted even if it exceeds min_length."""
        buffer = SentenceBuffer(min_sentence_length=20)

        long_sentence = (
            "This is a very long sentence that exceeds the minimum length threshold."
        )
        sentences = buffer.add_chunk(long_sentence)

        assert len(sentences) == 1
        assert sentences[0] == long_sentence

    def test_streaming_scenario(self):
        """Test realistic streaming scenario with incremental chunks."""
        buffer = SentenceBuffer(min_sentence_length=15)

        chunks = [
            "Hello,",
            " I'm Sarah.",
            " How can I",
            " help you",
            " today?",
            " Let me know",
            " what you need.",
        ]

        all_sentences = []
        for chunk in chunks:
            sentences = buffer.add_chunk(chunk)
            all_sentences.extend(sentences)

        # Get any remaining text
        remaining = buffer.flush()
        if remaining:
            all_sentences.append(remaining)

        # Should have extracted both sentences
        assert len(all_sentences) == 2
        assert "Hello, I'm Sarah. How can I help you today?" in all_sentences[0]
        assert "Let me know what you need." in all_sentences[1]

    def test_no_sentence_ending(self):
        """Test text without sentence ending punctuation."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("This has no ending")
        assert len(sentences) == 0

        # Should be in buffer
        assert buffer.buffer == "This has no ending"

        # Flush to get it
        remaining = buffer.flush()
        assert remaining == "This has no ending"

    def test_lowercase_abbreviations(self):
        """Test that lowercase abbreviations are handled."""
        buffer = SentenceBuffer(min_sentence_length=10)

        sentences = buffer.add_chunk("I visited dr. smith. He was great.")

        # Should recognize lowercase dr. as abbreviation
        assert len(sentences) == 2
        assert "dr. smith" in sentences[0].lower()
