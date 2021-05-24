# journal-dist-compare
## A CGI application for comparing journal citation distributions
This tool can be used to compare the citation distributions of up to four journals using citation count data provided through [CrossRef's public API](https://github.com/CrossRef/rest-api-doc). 

[A beta version of the tool is now live](https://alhufton.com/cgi-bin/journal-dist-compare.cgi).

All publications categorized in CrossRef as 'journal-article' are included. This may include corrections and editorial content, not just peer-reviewed papers. 

Citation counts are the total citations recorded for the entire lifetime of each publication. The time interval controls only which publications are considered from the selected journals. For example, if you select 2015 and a two-year interval, then papers published in 2015 and 2016 are included, but citations from anytime after publication will be counted (i.e. the citing works could be published anytime from 2015 to present).

Citation distributions are displayed as either [empirical cumulative distributions functions (eCDF)](https://en.wikipedia.org/wiki/Empirical_distribution_function) or as histograms with normalized frequencies. The display defaults to visualizing the distributions in log10 space.  

The hypothesis that the distributions are distinct is evaluated using pairwise [Kolmogorov-Smirnov tests](https://en.wikipedia.org/wiki/Kolmogorov-Smirnov_test).

For each journal, the top ten most cited articles are listed for the selected period, with links to [OpenCitations.net](https://opencitations.net/), where users can explore metadata on the citing articles if openly available.

For efficiency, the tool caches data for thirty days, which might introduce some small variation relative to the current CrossRef numbers.

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


