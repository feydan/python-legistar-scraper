from urllib.parse import urljoin, urlparse

import lxml.html

from legistar.base import Base, CachedAttr
from legistar.fields import FieldAggregator
from legistar import detailpage
import legistar.jurisdictions.config
from legistar.jurisdictions.base import Config, JXN_CONFIGS


class View(Base):
    '''Base class for Legistar views. Pass in a config_obj and
    either url or parse lxml.html doc.

    Each view has an associated top-level FormClass and TableClass
    that are used to submit the View's form and extract information.
    Those related classes as specificed in the jurisdiction's
    legistar.jxn_config.Config object, or in the default Config object.
    '''

    def __init__(self, url=None, doc=None):
        # Setting doc to None forces the view to fetch the page.
        self.chainmap['doc'] = doc

        # Allow the url to fall back to the parent chainmap url.
        if url is not None:
            self.chainmap['url'] = url

    # ------------------------------------------------------------------------
    # Managed attributes
    # ------------------------------------------------------------------------
    @property
    def sources_note(self):
        msg = 'Please set `sources_note` on this class: %r' % self.__class__
        raise NotImplementedError(msg)

    # ------------------------------------------------------------------------
    # Access to configable properties.
    # ------------------------------------------------------------------------
    @property
    def viewmeta(self):
        '''Return the view metadata for this View based on its PUPATYPE.
        '''
        return self.cfg.views.get_by_pupatype(self.PUPATYPE)

    @property
    def viewtype_meta(self):
        '''Return the viewtype metadata for this View based on its PUPATYPE
        and its VIEWTYPE, which is either 'search' or 'detail'.
        '''
        return getattr(self.viewmeta, self.VIEWTYPE)


class SearchView(View):

    def __iter__(self):
        '''Iterating over a search view generates tables of paginated search
        results.
        '''
        Form = self.viewtype_meta.Form
        yield from Form(self)


class DetailView(View, FieldAggregator):
    VIEWTYPE = 'detail'

    @CachedAttr
    def field_data(self):
        visitor = self.make_child(detailpage.Visitor)
        return visitor.visit(self.doc)

    def asdict(self):
        return dict(self)


class LegistarScraper(View):

    def gen_events(self):
        yield from self.gen_pupatype_objects('events')

    def gen_bills(self):
        yield from self.gen_pupatype_objects('bills')

    def gen_people(self):
        yield from self.gen_pupatype_objects('people')

    def gen_orgs(self):
        yield from self.gen_pupatype_objects('orgs')

    events = meetings = get_events = gen_events
    bills = legislation = get_bills = gen_bills
    people = members = get_people = gen_people
    orgs = organizations = committees = get_orgs = gen_orgs

    def get_pupatype_searchview(self, pupatype):
        '''Where pupa model is one of 'bills', 'orgs', 'events'
        or 'people', return a matching View subclass.
        '''
        tabmeta = self.cfg.tabs.get_by_pupatype(pupatype)
        url = urljoin(self.cfg.root_url, tabmeta.path)
        view_meta = self.cfg.views.get_by_pupatype(pupatype)
        view = view_meta.search.View(url=url)
        view.inherit_chainmap_from(self.cfg)
        return view

    def gen_pupatype_objects(self, pupatype):
        '''Given a pupa type, page through the search results and
        yield each object.
        '''
        yield from self.get_pupatype_searchview(pupatype)

    @classmethod
    def get_scraper(cls, *args, url=None, ocd_id=None, **kwargs):
        '''Get the correct scraper by url or ocd_id.
        '''
        config_type = None

        if url is not None:
            data = urlparse(url)
            try:
                config_type = JXN_CONFIGS[data.netloc]
            except KeyError:
                pass
        elif ocd_id is not None:
            try:
                config_type = JXN_CONFIGS[ocd_id]
            except KeyError:
                msg = ("There doesn't appear to be a scraper defined for "
                       "jurisdiction %s yet.")
                raise ScraperNotFound(msg % ocd_id)
        elif args:
            for key in args:
                if key in JXN_CONFIGS:
                    config_type = JXN_CONFIGS[key]
                    break

        if config_type is None:
            if url is not None:
                config_type = type('Config', (Config,), dict(root_url=url))
            else:
                raise Exception('Please supply the jurisdiction\'s url or ocd_id.')

        config_obj = config_type()
        scraper = cls(**kwargs)
        scraper.set_parent_chainmap(config_obj.chainmap)
        return scraper


class ScraperNotFound(Exception):
    pass