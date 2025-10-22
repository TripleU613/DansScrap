import dataclasses
from typing import List, Optional

import scrapy


class BoardInfoItem(scrapy.Item):
    board_id = scrapy.Field()
    name = scrapy.Field()
    description = scrapy.Field()
    topics = scrapy.Field()
    posts = scrapy.Field()
    url = scrapy.Field()


class TopicSummaryItem(scrapy.Item):
    board_id = scrapy.Field()
    board_offset = scrapy.Field()
    topic_id = scrapy.Field()
    subject = scrapy.Field()
    starter = scrapy.Field()
    replies = scrapy.Field()
    views = scrapy.Field()
    last_post_author = scrapy.Field()
    last_post_time = scrapy.Field()
    last_post_link = scrapy.Field()
    topic_url = scrapy.Field()
    page_url = scrapy.Field()


class PostItem(scrapy.Item):
    board_id = scrapy.Field()
    topic_id = scrapy.Field()
    post_id = scrapy.Field()
    position = scrapy.Field()
    author_name = scrapy.Field()
    author_profile = scrapy.Field()
    author_title = scrapy.Field()
    author_details = scrapy.Field()
    subject = scrapy.Field()
    posted_at = scrapy.Field()
    permalink = scrapy.Field()
    content_html = scrapy.Field()
    content_text = scrapy.Field()
    extracted_text = scrapy.Field()
    signature_html = scrapy.Field()
    signature_text = scrapy.Field()
    edited = scrapy.Field()
    likes = scrapy.Field()
    attachments = scrapy.Field()
    page_url = scrapy.Field()
