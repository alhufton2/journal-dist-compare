# journal-dist-compare
## A CGI application for comparing journal citation distributions
This tool can be used to compare the citation distributions of up to four journals using citation count data provided through [CrossRef's public API](https://github.com/CrossRef/rest-api-doc). [A beta version of the tool is now live](https://alhufton.com/cgi-bin/journal-dist-compare.cgi).

Citation distributions are displayed as either [empirical cumulative distributions functions (eCDF)](https://en.wikipedia.org/wiki/Empirical_distribution_function) or [probability mass functions (PMF)](https://en.wikipedia.org/wiki/Probability_mass_function). The eCDF options tends to offer more power to visualize real differences between the distributions, while the PMF option offers a histogram-like visualization that will be more familiar to many users. 

The display defaults to visualizing the distributions in log10 space.  

The hypothesis that the distributions are distinct is evaluated using pairwise [Kolmogorov-Smirnov tests](https://en.wikipedia.org/wiki/Kolmogorov-Smirnov_test).

## Dependencies
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


