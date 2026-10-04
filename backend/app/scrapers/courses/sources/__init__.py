"""
scrapers/courses/sources — Individual platform scraper modules.

Each module exposes a class that inherits BaseCourseSource and implements
the `fetch(keyword, max_results) -> list[dict]` contract.

Available sources:
    nptel      → app.scrapers.courses.sources.nptel.NPTELSource
    swayam     → app.scrapers.courses.sources.nptel.SWAYAMSource
    mit_ocw    → app.scrapers.courses.sources.mit_ocw.MITOCWSource
    edx        → app.scrapers.courses.sources.edx.EdXSource
    coursera   → app.scrapers.courses.sources.coursera.CourseraSource
    udemy      → app.scrapers.courses.sources.udemy.UdemySource
"""
