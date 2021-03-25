#!/usr/bin/perl

# use the shebang line below when running at bluehost
#   !/usr/bin/perlml

use strict;
use warnings;
use utf8;

use CGI::Carp qw(fatalsToBrowser set_message);
BEGIN {
   sub handle_errors {
      my $msg = shift;
      print "<h1>A serious error occurred</h1>";
      print "<p>The following error message was generated: $msg</p>";
  }
  set_message(\&handle_errors);
}

# Load CGI webform package and create a handler
use CGI::Simple;
$CGI::Simple::NO_UNDEF_PARAMS = 1;
my $q = CGI::Simple->new;
$q->charset('utf-8');      # set the charset
$q->no_cache(1);
my $tool_url = $q->url();
my $query_url = $q->url('-absolute'=>1, '-query'=>1);

# Load other packages
use CHI; 
use Encode;
use Proc::Daemon;
use Statistics::Descriptive::Discrete;
use HTML::Table;
use Business::ISSN;
use LWP::UserAgent;
use JSON::MaybeXS;
use open qw( :encoding(UTF-8) :std );
binmode(STDOUT, ":utf8");

# Open the cache
my $tempdir_path = '/Users/alhufton/Sites/tmp';
# my $tempdir_path = '/home3/alhufton/tmp/journal-compare';
my $cache = CHI->new( driver => 'File', root_dir => $tempdir_path );

# Set various variables
my $max_interval = 3; # maximum year interval allowed. 
my $contact_email = 'enter email address';
my $timeout = 300;
my $cache_time = '7 days';
my $top_num = 10; 
my $json = JSON::MaybeXS->new->pretty;  # creates a json parsing object
my $uaheader = "Journal Distribution Compare Tool/beta (https://alhufton.com; mailto:$contact_email)";
my $alpha = 0.05; 

# main parameter variables
my @issn_clean;
my $start_year;
my $end_year;
my $log;
my $chart;

# main data variables
my %citation_counts; # ISSN->Stat Discrete obj
my %top_pubs;        # array per ISSN of CrossRef items, top ten guaranteed to be sorted

# Main body 
print $q->header();
start_html();
print_header();
print_menu();

# Open the central portion of the page, which will consist of two columns
opendiv("row");
	
# Parse parameters, and create the content in the main righthand column
opendiv("column-main");
my $error = 0;
if ( $q->param ) { 
	if ( clean_parameters($q) ) {
		make_results() if load_data();
	} else { $error = 1; }
} elsif ( $error == 0 ) {
    $log = 1;
	print_intro();
}
closediv();	# close main column

# Create lefthand entry form
opendiv("column-side");
print_prompt();
closediv(); # close column side
closediv(); # close row
print_tail();

exit;

sub clean_parameters {
    my $form = shift;
    
    # Process and clean the ISSNs 
    if ( $form->param('ISSN') ) {
        foreach ( $form->param('ISSN') ) {
            s/\s+//g; 
            my $issn_object = Business::ISSN->new($_);
            if ( $issn_object && $issn_object->is_valid() ) { push @issn_clean, $issn_object->as_string; }
            else { print "<p>WARNING: ISSN ($_) is invalid</p>"; }
        }
    }
    
    # Checks
    unless ( @issn_clean ) { print "<p>No valid ISSNs provided.</p>"; return 0; }
    unless ( $form->param('interval') <= $max_interval ) { print "<p>Selected interval exceeds maximum allowed.</p>"; return 0; }
    
    $start_year = $form->param('start_year');
    $end_year = $start_year + $form->param('interval') - 1;
    if ( $form->param('log') ) { $log = 1 } 
    else { $log = 0 }
    $chart = 'ecdf';
    if ( $form->param('chart') && $form->param('chart') eq 'pmf' ) { $chart = 'pmf' }

    return 1; 
}

# Load data from the cache into the main variables
sub load_data { 
	
    my $status_table = new HTML::Table( -class=>'bordered', -head=>['ISSN', 'Year', 'Status'] );	
    $status_table->setRowHead(1);
    my $success = 1;
    my $fail = 0;
    
    # First check if any data need to be downloaded
    foreach my $issn ( @issn_clean ) {
    	my @results;
    	foreach my $year ($start_year .. $end_year) {
    		my $cache_id = "$year-$issn";
    		my $cache_results = $cache->get($cache_id);
    		if ( defined $cache_results && ref $cache_results ) {
    			$status_table->addRow($issn, $year, 'Cached');
    		} elsif ( defined $cache_results && length $cache_results ) {
    			$status_table->addRow($issn, $year, $cache_results);
    			$success = 0;
    			unless ( $cache_results eq 'Downloading' ) { $fail = 1; }
    		} else {
    			$status_table->addRow($issn, $year, 'Initiating download');
    			get_crossref_metadata($issn,$year,$uaheader); 
    			$success = 0;
    		}
    	}
    }
    
    # If all are successfully in the cache, proceed to load the data 
	if ( $success ) {
		foreach my $issn ( @issn_clean ) {
			my @results;
			foreach my $year ($start_year .. $end_year) {
				my $cache_id = "$year-$issn";
				my $cache_results = $cache->get($cache_id);
				push @results, @$cache_results;
			}
	
			$citation_counts{$issn} = new Statistics::Descriptive::Discrete;
			
			my $min;
			foreach my $item ( @results ) {
				if ( $item->{'is-referenced-by-count'} ) {
				   $citation_counts{$issn}->add_data($item->{'is-referenced-by-count'});
 
					### partial sorting algorithm ######
					my $k = 0;
					my $added = 0;
					if ( ! defined $min || $item->{'is-referenced-by-count'} > $min ) {
						foreach my $item2 ( @{$top_pubs{$issn}} ) {
							last if ( $k > $top_num );
							if ( $item->{'is-referenced-by-count'} >= $item2->{'is-referenced-by-count'} ) {
								splice @{$top_pubs{$issn}}, $k, 0, $item;
								pop @{$top_pubs{$issn}} if ( @{$top_pubs{$issn}} > $top_num ); 
								$min = $item->{'is-referenced-by-count'} if ( $item->{'is-referenced-by-count'} < $min );
								$added = 1;
								last;
							}
							++$k;
						}
					}
					if ( $added == 0 && @{$top_pubs{$issn}} < $top_num ) { 
						push @{$top_pubs{$issn}}, $item;
					}         
					####################################          
					
				} else {
					$citation_counts{$issn}->add_data(0);
				}
			}
		} 
		return 1;  
	} else {
    	if ($fail) {
    		print "<h2>Failed to obtain all citation data</h2>\n";
    		print $status_table->getTable();
    		print_fail_message(); 
    	} else { 
    		print "<h2>Citation data downloading</h2>\n";
    		print $status_table->getTable();
    		print_reload_message(); 
    	}
    	return 0;
    }
}

sub make_results {
    
    my %ecdf; # hash of arrays. Always generated
    my %pmf;  # hash of arrays. Only generated if chart = 'pmf'
    my %n;
    my @results_HTML;
    my $j_num = scalar @issn_clean;
    
    # Place the distribution chart
    print "<div id=\"results\">\n";
    if ( $chart eq 'ecdf' ) {
        my $pmf_link = $query_url;
        if ( $pmf_link =~ /chart=ecdf/ ) {
            $pmf_link =~ s/chart=ecdf/chart=pmf/;
        } else {
            $pmf_link .= "&chart=pmf";
        }
        print "<h2>Empirical cumulative distribution function (eCDF)</h2>\n";
        print "<p>Each point represents the fraction of papers (<em>y</em>) that have <em>x</em> or fewer citations. 
        You may also view the distribution as a <a href=\"$pmf_link\">Probability Mass Function (PMF)</a>, a 
        non-cumulative histogram-like representation. Click on the journal names below to toggle their display.</p>\n";
    } elsif ( $chart eq 'pmf' ) {
        my $ecdf_link = $query_url;
        $ecdf_link =~ s/chart=pmf/chart=ecdf/;
        print "<h2>Probability mass function (PMF)</h2>\n"; 
        print "<p>Each point represents the fraction of papers (<em>y</em>) that have exactly <em>x</em> citations.  
        You may also view the distribution as an <a href=\"$ecdf_link\">Empirical Cumulative Distribution Function 
        (eCDF)</a>, which generally offers more power to see genuine differences in the distributions. Click on the 
        journal names below to toggle their display.</p>\n";
    } 
    print  "<canvas id=\"myChart\"></canvas>\n";
        
    # output some basic summary stats
    print "<h2>Summary statistics</h2>\n";
    print "<p>for journal articles published in $start_year";
    if ($end_year == $start_year) { print "</p>\n"; }
    else { print " to $end_year</p>\n"; }
    my $stattable = new HTML::Table( -class=>'bordered', -head=>['Journal', 'ISSN', 'Count', 'Mean', 'Median', 'Variance'] );
    $stattable->setRowHead(1);
   
    foreach my $issn ( @issn_clean ) {
        $n{$issn} = $citation_counts{$issn}->count();
        my @uniqs = $citation_counts{$issn}->uniq(); 
        my $f = $citation_counts{$issn}->frequency_distribution_ref(\@uniqs);
        my $i = 0;
        foreach ( @uniqs ) {
            $i += $f->{$_};
            $ecdf{$issn}->[$_] = $i/$n{$issn};
            if ( $chart eq 'pmf') {
                $pmf{$issn}->[$_] = $f->{$_}/$n{$issn};
            }
        } 
        
        $stattable->addRow(
            $top_pubs{$issn}->[0]->{'container-title'}->[0],
            $issn, 
            $n{$issn}, 
            sprintf("%.2f", $citation_counts{$issn}->mean()), 
            $citation_counts{$issn}->median(), 
            sprintf("%.2f", $citation_counts{$issn}->variance())
            );
    }
    print $stattable->getTable();
   
    if ( $j_num > 1 ) {
        
        # Running the Kolmogorov-Smirnov pairwise tests
        print "<h3>Kolmogorov-Smirnov tests</h3>\n";
        my @short_journal_names;
        foreach my $issn (@issn_clean) {
            if ( $top_pubs{$issn}->[0]->{'short-container-title'}->[0] ) {
                push @short_journal_names, $top_pubs{$issn}->[0]->{'short-container-title'}->[0];
            } else {
                push @short_journal_names, $top_pubs{$issn}->[0]->{'container-title'}->[0];
            }
        }
        my $pairtable = new HTML::Table( -class=>'bordered', -width=>'70%', -data=>[['', @short_journal_names]] );
        
        my $col_width = 100/(@issn_clean+1);
        
        # Calculate a Bonferroni corrected alpha
        my $c_alpha = $alpha; 
        $c_alpha /= 3 if ($j_num == 3);
        $c_alpha /= 6 if ($j_num == 4);
        
        my $k = 1;
        my %inverseD;
        my %inverse_flag;
        foreach my $issn1 (@issn_clean) {
            my $i = 1;
            my $r = $k + 1;
            my $jname = shift @short_journal_names;
            $pairtable->setCell($r,1,$jname);
            foreach my $issn2 (@issn_clean) {
                my $c = $i + 1;
                my $D = 0;
                my $flag = 0;
                if ( $k == 1) { $pairtable->setColWidth($c, "$col_width\%") }
                my $cell_content = 'ERROR';
                
                if ( $issn1 eq $issn2 ) {
                    $cell_content = '-';
                } elsif ( defined $inverseD{$issn1}->{$issn2} ) {
                    $D = $inverseD{$issn1}->{$issn2};
                    $flag = $inverse_flag{$issn1}->{$issn2};
                    $cell_content = sprintf("%.4g", $D);
                    $cell_content .= '*' if ( $flag );
                } else {
                    ($D, $flag) = &KS_test_discrete( $ecdf{$issn1}, $n{$issn1}, $ecdf{$issn2}, $n{$issn2}, $c_alpha );
                
                    $cell_content = sprintf("%.4g", $D);
                    $cell_content .= '*' if ( $flag );
                    $inverseD{$issn2}->{$issn1} = $D;
                    $inverse_flag{$issn2}->{$issn1} = $flag;
                }
                
                $pairtable->setCell($r,$c,$cell_content);
                
                # set cell color
                my $hue = 255*$D;
                my $text_hue = 0;
                if ( $hue < 150 ) { $text_hue = 210 }
                if ( $hue < 50 )  { $text_hue = 153 }
                my $color_bias = $hue * 0.75;
                $pairtable->setCellStyle($r, $c, "color: rgb($text_hue,$text_hue,$text_hue); background-color: rgb($hue,$color_bias,$hue)");
                ++$i;
            }
            ++$k;
        }
        print $pairtable->getTable(); 
        print "<p>D values for the pairwise tests are shown (the higher the number, the more different are the journals' citation distributions). An '*' indicates that the difference is significant after Bonferroni correction at an alpha value of $alpha.</p>";
    }
    
    # Create top ten lists
    print "<h2>Top $top_num cited papers for each journal</h2>\n";
    print "<p>CrossRef citation counts are provided in parentheses. <a href=\"http://opencitations.net/\"><span style=\"color:rgb(153, 49, 252)\">Open</span><span style=\"color:rgb(45, 34, 222)\">Citations</span></a>
    links can be used to search for open metadata on the citing articles, if available, through the OpenCitations.net service built by researchers at the University 
    of Bologna and University of Oxford.</p>\n";
    foreach my $issn ( @issn_clean ) {
        print "<h3>$top_pubs{$issn}->[0]->{'container-title'}->[0]</h3>\n";
        print "<ol>\n";
        foreach ( @{$top_pubs{$issn}} ) {
            my $doi = $_->{'DOI'};
            my $title = $_->{'title'}->[0];
            my $is_ref_by = $_->{'is-referenced-by-count'};
            my $safe_doi = $q->url_encode($doi);
            my $occ_search = "https://opencitations.net/search?text=$safe_doi&rule=doi";
            print "<li><div style=\"float:left;width:80%;\"><a href=\"https://doi.org/$doi\" target=\"_blank\">$title</a> ($is_ref_by)</div><div style=\"float:right;\"><a href=\"$occ_search\" target=\"_blank\"><span style=\"color:rgb(153, 49, 252)\">Open</span><span style=\"color:rgb(45, 34, 222)\">Citations</span></a></div><div style=\"clear:both;\"></div></li>\n";
        }
        print "</ol>\n";
    }
    
    if ( $chart eq 'pmf' ) {
        drawChart (\%pmf);
    } else {
        drawChart (\%ecdf);
    }
    closediv();
}


# Writes a Chart.js javascript with cumulative distribution plots
sub drawChart {
    my %ecdf = %{$_[0]}; 
    my $x_scale;
    my $log_label = '';

    if ($log) { 
        $x_scale = 'logarithmic';
        $log_label = " (log10)";
    } else { $x_scale = 'linear' }
    
    my $yaxis_label = "Cumulative probability";
    my $xaxis_label = "Citations to paper since publication$log_label";
    if ( $chart eq 'pmf' ) {
        $yaxis_label = "Probability";
        $xaxis_label = "Citations to paper since publication$log_label";
    }
    
    # Define the colors that will be used for the four data series
    my @bgcolors = (
        "rgba(153,255,51,0.6)",
        "rgba(0,51,204,0.6)",
        "rgba(252, 174, 30,0.6)",
        "rgba(190,0,220,0.6)",
        );
    
###### start the Chart.js script #
    print <<EOF;
<script>
Chart.defaults.global.defaultFontColor = "rgb(190,190,190)";
var ctx = document.getElementById('myChart').getContext('2d');
var myChart = new Chart(ctx, {
  type: 'scatter',
  data: {
       datasets: [  
EOF
#############################

    my $k = 0; 
    foreach my $issn (@issn_clean) {

        print "," if $k;
        
####### start a new data series

    if ( $chart eq 'ecdf' ) {
       print <<EOF;
        {
           label: '$top_pubs{$issn}->[0]->{'container-title'}->[0]',
           steppedLine: 'after',
           showLine: 'true',
           backgroundColor: "$bgcolors[$k]",
           data: [
EOF
    } elsif ( $chart eq 'pmf' ) {
        print <<EOF;
        {
           label: '$top_pubs{$issn}->[0]->{'container-title'}->[0]',
           showLine: 'true',
           backgroundColor: "$bgcolors[$k]",
           data: [
EOF
    }
##############################
        ++$k;
            
        my $i = 0;
        my $max = $#{$ecdf{$issn}};
        foreach ( 0 .. $max ) {
            if ( defined $ecdf{$issn}->[$_] ) {
                my $y = sprintf("%.3f", $ecdf{$issn}->[$_]);
                print "," if $i; ++$i; 
                print "             {x: $_, y: $y}";
            }
        }
        print "           ]
        }"; #closes data
    }
    print "
      ]},\n"; #closes datasets

######## Style the axes and add axis labels      
    print <<EOF;
      options: {
        legend: {
            display: true,
            labels: {
                fontSize: 16
            }
        },
        scales: {
          xAxes: [{
             type: '$x_scale',
             position: 'bottom',
             scaleLabel: {
                labelString: '$xaxis_label',
                display: 'true',
                fontSize: 16
             },
             gridLines: { 
                color: 'rgb(50,50,50)'
             },
          }],
          yAxes: [{
             type: 'linear',
             position: 'left',
             scaleLabel: {
                labelString: '$yaxis_label',
                display: 'true',
                fontSize: 16
             },
             ticks: { suggestedMin: 0 },
             gridLines: { 
                color: 'rgb(50,50,50)'
             },
          }]
        }
    }
});
</script>
EOF
#############################
}


# a valid ISSN and year, and the uaheader
sub get_crossref_metadata {
    my $issn = shift;
    my $year = shift;
    my $uaheader = shift;
    my @results; # array of hashes with {title, doi, is-referenced-by-count} 
    my $cache_id = "$year-$issn";
    
    # Place a marker in the cache to let other runs know we are downloading citation metadata for this journal & year
    my $max_download_time = $timeout + 60;
    $cache->set($cache_id, 'Downloading', $max_download_time);
    
    # Establish daemon settings to fork off download operations
    my $daemon = Proc::Daemon->new(
    	work_dir => $tempdir_path,
    	child_STDOUT => ">>$tempdir_path/stdout.txt",
    	child_STDERR => ">>$tempdir_path/stderr.txt",
    );
    
    my $child_1_PID = $daemon->Init;
 
    unless ( $child_1_PID ) {

		my $ua = LWP::UserAgent->new;
		$ua->timeout($timeout);
		$ua->agent($uaheader); 
		
		my $result_num = 0;
		my $first = 1;
		my $next_cursor = '*'; 
		print "Attempting to obtain citation data from CrossRef for ISSN $issn in year $year.\n";
	
		while ( $result_num > 0 || $first ) {
			my $rows; 
			my $response = $ua->get(
				"https://api.crossref.org/journals/$issn/works?filter=from-pub-date:$year,until-pub-date:$year,type:journal-article&rows=1000&select=DOI,title,is-referenced-by-count,container-title,short-container-title&cursor=$next_cursor"
				);
			if ($response->is_success) {
				my $metadata = decode_json $response->content;
				if ( $first ) {
					$first = 0;
					if ( $metadata->{'message'}->{'total-results'} ) { $result_num = $metadata->{'message'}->{'total-results'}; }
					if ( $result_num == 0 ) { print "<p>WARNING: No results for $issn in $year.</p>\n"; $cache->set($cache_id, "Failed (No results)", $timeout); exit; }
				}
				if ( $metadata->{'message'}->{'next-cursor'} ) { $next_cursor = $q->url_encode($metadata->{'message'}->{'next-cursor'}); }
				if ( @{$metadata->{'message'}->{'items'}} ) {
					foreach my $item ( @{$metadata->{'message'}->{'items'}} ) {
						push @results, $item;
					}
				}
			} else { 
				my $fail_message = "Failed (" . $response->status_line . ").";
				print "WARNING: CrossRef call failed for $issn. $fail_message.\n";
				$cache->set($cache_id, $fail_message, $timeout);
				exit;
			}
			$result_num -= 1000;
		}
		if ( @results ) {
			$cache->set($cache_id, \@results, $cache_time);
			print "Citation data for ISSN $issn for year $year successfully downloaded.\n";
		}
		exit;
	}
}

sub KS_test_discrete {
    my @ecdf1 = @{$_[0]};
    my $n1 = $_[1];
    my @ecdf2 = @{$_[2]};
    my $n2 = $_[3];
    my $alpha = $_[4];
    
    my $D = 0;
    my $Dcrit = sqrt(-log($alpha/2) * 0.5) * sqrt(($n1+$n2)/($n1*$n2));
    my $max;
    
    if ( $#ecdf1 > $#ecdf2 ) {
        $max = $#ecdf1;
    } else {
        $max = $#ecdf2;
    }
    
    my $f1 = 0;
    my $f2 = 0;
    foreach ( 0 .. $max ) {
        if ( defined $ecdf1[$_] ) { $f1 = $ecdf1[$_] }
        if ( defined $ecdf2[$_] ) { $f2 = $ecdf2[$_] }
        
        my $tempD = abs( $f1 - $f2 );
        $D = $tempD if ( $tempD > $D );
    }
    #print "Comparing D $D to Dcrit $Dcrit, where n is $n1 and m $n2, at alpha $alpha.\n";
    if ( $D > $Dcrit ) {
        return $D, 1;
    } else {
        return $D, 0;
    }
}

sub shuffle {
    my $deck = shift;  # $deck is a reference to an array
    return unless @$deck; # must not be empty!

    my $i = 3;
    my $k = @$deck;
    while ($i >= 0 ) {
        my $j = int rand ($k);
        @$deck[$i,$j] = @$deck[$j,$i];
        --$i;
    }
}

############################
# HTML writing subroutines #
############################

sub start_html {
    print <<EOF;

<head>
<title>Compare Journal Citation Distributions</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/2.9.4/Chart.min.js"></script>
<link rel="stylesheet" href="../css/tool.css">
</head>
<body onLoad="timeRefresh(10000);">
    
EOF

}

sub opendiv {
    my $class = shift;
    print "<div class=\"$class\">\n";
}

sub closediv {
    print "</div>\n";
}

sub print_reload_message {
	print <<EOF;
	<p>Downloading data from CrossRef. This could take several minutes. Results 
	will be automatically displayed when complete. You can bookmark this page, 
	and close the window, if you want to check back on the results later.</p>

	<script>
      function timeRefresh(time) {
        setTimeout("location.reload(true);", time);
      }
    </script>
EOF
}

sub print_fail_message {
	
	print <<EOF;
<p>Errors were encountered while trying to download some of the requested citation data. 
'No results' may indicate that your journal of interest had no publications in the selected year, 
or that the ISSN you used isn't the one the journal uses in its CrossRef metadata. 
If a journal has more than one ISSN, 'print' version is usually the one recognized 
by CrossRef. 500 errors may simply indicate a timeout problem due to a slow connection. 
Hit 'Go' again to retry.</p>
EOF

}


sub print_header {
    print "<div class=\"header\"><h1><a href=\"$tool_url\">Compare journal citation distributions</a></h1></div>\n";
}

sub print_tail {
    print <<EOF;  
<div class="footer">
<p><a href="https://alhufton.com/">Home</a> 
| <a href="mailto:$contact_email">Contact</a> 
| <a href="https://github.com/alhufton2/">GitHub</a></p>
<p>© 2020 Andrew Lee Hufton</p>
<p><a href="https://alhufton.com/privacy-policy/">Privacy policy</a></p>
</div>
</body>
</html>

EOF

}
    
sub print_intro {
    my @issn_rand = ('0098-7484', '2052-4463', '1548-7105', '1866-3516', '1537-1719', '2046-1402', '1095-9203', '2054-5703', '2190-4286', '1097-2765', '1759-4812', '0305-1048', '1944-8007', '1313-2970', '1053-8119', '1368-423X', '1662-453X');
    &shuffle(\@issn_rand);
    my $year_rand = 2015 + int rand(4);
    
    print <<EOF;
    
<div class="intro">
  <p>Compare the citation distributions for up to four selected journals using 
  publically available citation data from the <a href="https://github.com/CrossRef/rest-api-doc">CrossRef API</a>. 
  Enter the ISSN for each journal of interest. <a href="https://portal.issn.org/">Find journal ISSNs here.</a>
  All publications categorized as 'journal-article' by CrossRef are included. 
  Please note that this is likely to include corrections and editorial content, 
  not just peer-reviewed research articles. Citation counts are the total 
  citations recorded for the entire lifetime of each publication.</p>
  
  <p>Please note that it could take up to several minutes for the results to be 
  generated, especially if you are comparing journals with thousands of 
  publications per year.</p> 
  
  <p>The hypothesis that the distributions are distinct is evaluated using pairwise 
  <a href="https://en.wikipedia.org/wiki/Kolmogorov-Smirnov_test">Kolmogorov-Smirnov 
  tests</a>.</p> 
  
  <p>For efficiency, the tool caches data for seven days, which might introduce 
  some small variation relative to the current CrossRef numbers.</p>
  
  <p>Try a <a href="$tool_url?ISSN=$issn_rand[0]&ISSN=$issn_rand[1]&ISSN=$issn_rand[2]&ISSN=$issn_rand[3]&start_year=$year_rand&interval=1&log=true">Random Example</a>!</p>
</div>

EOF

}

sub print_prompt {
    
    my @issn_value;
    my $default_year = 2000;
    if ( $start_year ) { $default_year = $start_year;} 
    my $log_checked = " checked=\"true\"" unless ( $log == 0 );
    my $ecdf_checked = " checked=\"checked\"" unless ( $chart eq 'pmf' );
    my $pmf_checked = " checked=\"checked\"" if ( $chart eq 'pmf' );
    
    foreach (0..3) {
        unless ( defined $issn_clean[$_] ) {
            $issn_value[$_] = "";
        } else {
            $issn_value[$_] = $issn_clean[$_];
        }
    }
    
    my $interval_opt ='';
    foreach (0..$max_interval - 1) {
        my $num = $_ + 1;
        unless ($num == $q->param('interval') ) { $interval_opt .= "<option>$num</option>\n"; }
        else { $interval_opt .= "<option selected=\"selected\">$num</option>\n"; }
    }
            
    # print the form    
    print <<EOF;
<form> 
  <h3>Journal ISSNs</h3>
  <p><input type="text" name="ISSN" size="15" maxlength="50" value="$issn_value[0]">
    <input type="text" name="ISSN" size="15" maxlength="50" value="$issn_value[1]">
    <input type="text" name="ISSN" size="15" maxlength="50" value="$issn_value[2]">
    <input type="text" name="ISSN" size="15" maxlength="50" value="$issn_value[3]"></p>

  <h3>Publication years</h3>
  <p>start year&nbsp;<select id="year" name="start_year" required="true"></select></br>
  interval (yrs)&nbsp;<select id="interval" name="interval">$interval_opt</select></br>
  <h3>Display options</h3>
  <p><input type="radio" id="option1" name="chart" value="ecdf"$ecdf_checked>
  <label for="option1">eCDF</label>
  <input type="radio" id="option2" name="chart" value="pmf"$pmf_checked>
  <label for="option2">PMF</label><br>  
  <input style="display:inline" type="checkbox" id="log" name="log" value="true"$log_checked>
  <label for="log">logarithmic&nbsp;</label></p>
  
  <div class="button">
    <input type="submit" value="Go!" style="font-size : 20px;">
  
<script type="text/javascript"> 
    //<![CDATA[ 
    var start = 1900; 
    var end = new Date().getFullYear(); 
    select = document.getElementById("year");
    for(var year = start ; year <=end; year++){ 
        var opt = document.createElement('option');
        opt.value = year;
        opt.innerHTML = year;
        if ( year == $default_year ) {
            opt.selected = "selected";
        }
        select.appendChild(opt);
    }
    //]]>
</script>

  </div>
</form>
	
EOF

}

sub print_menu {
    print <<EOF;
<div class="nav"><p><a href="https://alhufton.com">home</a> &#9657; <a href="https://alhufton.com/tools/">tools</a> &#9657; journal compare tool</p></div>
EOF
}