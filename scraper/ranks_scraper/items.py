import scrapy


class FetchedSourceItem(scrapy.Item):
    """Fetched + parsed source payload for ranks FE / Postgres snapshot."""

    name = scrapy.Field()
    url = scrapy.Field()
    browse_url = scrapy.Field()
    kind = scrapy.Field()
    spider = scrapy.Field()
    ok = scrapy.Field()
    status = scrapy.Field()
    body = scrapy.Field()
    bytes = scrapy.Field()
    elapsed_ms = scrapy.Field()
    fetched_at = scrapy.Field()
    source_date = scrapy.Field()
    error = scrapy.Field()
    engine = scrapy.Field()
    # Parsed FE-facing fields
    rankings = scrapy.Field()
    models = scrapy.Field()
    mentions = scrapy.Field()
