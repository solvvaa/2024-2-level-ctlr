"""
Crawler implementation.
"""
import datetime
import json

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import pathlib

#import pathlib
import shutil
from asyncio import timeout
from typing import Pattern, Union

import requests
from bs4 import BeautifulSoup

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH

#import json






class IncorrectSeedURLError(Exception):
    """
    Raises when seed URL does not match standard pattern
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
        Raises when total number of articles is out of range from 1 to 150
        """


class IncorrectNumberOfArticlesError(Exception):
    """
        Raises when total number of articles to parse is not integer or less than 0
        """


class IncorrectHeadersError(Exception):
    """
        Raises when headers are not in a form of dictionary
        """


class IncorrectEncodingError(Exception):
    """
        Raises when encoding is not specified as a string
        """


class IncorrectTimeoutError(Exception):
    """
        Raises when timeout value is not a positive integer less than 60
        """


class IncorrectVerifyError(Exception):
    """
        Raises when verify certificate value is not either True or False
        """


class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        self.path_to_config = path_to_config
        config = self._extract_config_content()
        self._seed_urls = config.seed_urls
        self._num_articles = config.total_articles
        self._headers = config.headers
        self._encoding = config.encoding
        self._timeout = config.timeout
        self._should_verify_certificate = config.should_verify_certificate
        self._headless_mode = config.headless_mode
        self._validate_config_content()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, encoding='utf-8') as file:
            config_dto = json.load(file)
            return ConfigDTO(**config_dto)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        if (not isinstance(self._seed_urls, list)
                or not all(isinstance(url, str) for url in self._seed_urls)):
            raise IncorrectSeedURLError('_seed_urls must be a list')
        if not all(url.startswith('http://www.') for url in self._seed_urls):
           raise IncorrectSeedURLError('Seed URL does not match standard pattern')
        if (not isinstance(self._num_articles, int) or isinstance(self._num_articles, bool)
                or self._num_articles < 0):
            raise IncorrectNumberOfArticlesError('Invalid number pf articles: '
                                       'must be an integer and not 0')
        if self._num_articles > 150:
            raise NumberOfArticlesOutOfRangeError('Number of articles out of range: '
                                        'should be between 1 and 150')
        if not isinstance(self._encoding, str):
            raise IncorrectEncodingError('Encoding is not specified as a string')

        if (not isinstance(self._timeout, int)
                or not 0 < self._timeout<60):
            raise IncorrectTimeoutError('Timeout value is not a positive integer less than 60')

        if not isinstance(self._should_verify_certificate, bool):
            raise IncorrectVerifyError('Verify certificate value is npt either True or False')

        if not isinstance(self._headless_mode, bool):
            raise IncorrectVerifyError('headless_mode should be an instance of bool')

        if not isinstance(self._headers, dict):
            raise IncorrectHeadersError('Headers are not in a form of dictionary')


    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self._seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self._num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self._headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self._encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self._timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self._should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._headless_mode


def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """
    if not isinstance(url, str):
        raise ValueError('URL is not a str')
    response = requests.get(url,
                            headers=config.get_headers(),
                            timeout=config.get_timeout(),
                            verify=config.get_verify_certificate()
                            )
    response.encoding = config.get_encoding()
    return response


class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: Union[Pattern, str]

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls = []

    def _extract_url(self, article_bs: BeautifulSoup) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.BeautifulSoup): BeautifulSoup instance

        Returns:
            str: Url from HTML
        """
        all_links = article_bs.find_all('a', href=True)
        for link in all_links:
            if link is None:
                return ""
            href = str(link['href'])
            if href.startswith('/news'):
                full_url = 'http://www.novkamen.ru' + href
                link.decompose()
                if isinstance(full_url, str):
                    return full_url
        return 'stop iteration'


    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.get_search_urls():
            if len(self.urls) >= self.config.get_num_articles():
                break
            response = make_request(seed_url, self.config)
            if response and response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                while True:
                    url = self._extract_url(soup)
                    if url == 'stop iteration' or url in self.urls:
                        break
                    self.urls.append(url)
                    if len(self.urls) >= self.config.get_num_articles():
                        return

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


# 10
# 4, 6, 8, 10


class HTMLParser:
    """
    HTMLParser implementation.
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """
        self.full_url = full_url
        self.article_id = article_id
        self.config = config
        self.article = Article(url = full_url, article_id = article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup, paragraps=None) -> None:

        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        paragraphs = article_soup.find_all('p', class_=lambda class_name: True)
        article_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs)
        self.article.text = article_text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        article_title = article_soup.find('h1', class_=lambda class_name: True)
        self.article.title = article_title.get_text(strip=True)
        author = article_soup.find_all('span', class_=lambda class_name: class_name and class_name.startswith('mr-2'))
        if author and len(author) > 0:
            self.article.author = [author[-1].get_text(strip=True)]
        else:
            self.article.author = ["NOT FOUND"]

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """

    def parse(self) -> Union[Article, bool, list]:
        """
        Parse each article.

        Returns:
            Union[Article, bool, list]: Article instance
        """
        response = make_request(self.full_url, self.config)
        if not response.ok:
            return self.article

        article_bs = BeautifulSoup(response.text, 'lxml')
        self._fill_article_with_text(article_bs)
        self._fill_article_with_meta_information(article_bs)
        return self.article


def prepare_environment(base_path: Union[pathlib.Path, str]) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (Union[pathlib.Path, str]): Path where articles stores
    """
    base_path = pathlib.Path(base_path)
    if base_path.exists():
        shutil.rmtree(base_path)
    base_path.mkdir(parents=True, exist_ok=True)

def main() -> None:
    """
    Entrypoint for scrapper module.
    """
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()
    for i, full_url in enumerate(crawler.urls):
        parser = HTMLParser(full_url=full_url, article_id=i + 1, config=configuration)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)

if __name__ == "__main__":
    main()
