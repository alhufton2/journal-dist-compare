# journal-dist-compare
## A CGI application for comparing journal citation distributions
This tool can be used to compare the citation distributions of up to four journals using citation count data provided through [CrossRef's public API](https://github.com/CrossRef/rest-api-doc). All publications categorized as 'journal-article' by CrossRef are included. This may include corrections and editorial content, not just peer-reviewed content. Citation counts are the total citations recorded for the entire lifetime of each publication.

[A beta version of the tool is now live](https://alhufton.com/cgi-bin/journal-dist-compare.cgi).

Citation distributions are displayed as either [empirical cumulative distributions functions (eCDF)](https://en.wikipedia.org/wiki/Empirical_distribution_function) or [probability mass functions (PMF)](https://en.wikipedia.org/wiki/Probability_mass_function). The eCDF option offers more power to visualize real differences between the distributions, while the PMF option provides a histogram-like visualization that will be familiar to more users. The display defaults to visualizing the distributions in log10 space.  

The hypothesis that the distributions are distinct is evaluated using pairwise [Kolmogorov-Smirnov tests](https://en.wikipedia.org/wiki/Kolmogorov-Smirnov_test).

For each journal, the top ten most cited articles are listed for the selected period, with links to OpenCitations.net](https://opencitations.net/), where users can explore metadata on the citing articles if openly available. The OpenCitations links are currently deactivated on the public beta version.

For efficiency, the tool caches data for seven days, which might introduce some small variation relative to the current CrossRef numbers.

## Dependencies
- Chart.js
- CHI
- Encode
- CGI::Simple
- CGI::Carp
- Proc::Daemon
- Statistics::Descriptive::Discrete
- HTML::Table
- Business::ISSN
- LWP::UserAgent
- JSON::MaybeXS


