"""
scrapers/courses — Course metadata extraction pipeline.

Quick-start:
    from app.scrapers.courses import CourseScraper, CourseScraperRequest

    req = CourseScraperRequest(
        keyword="machine learning",
        max_results=50,
        sources=["nptel", "swayam", "mit_ocw", "edx", "coursera", "udemy"],
    )
    courses: list[dict] = CourseScraper(req).run()
"""

from app.scrapers.courses.course_scraper import CourseScraper, CourseScraperRequest  # noqa: F401

__all__ = ["CourseScraper", "CourseScraperRequest"]
