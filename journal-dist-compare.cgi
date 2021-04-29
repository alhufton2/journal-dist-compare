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
my $max_journals = 4;
my $contact_email = 'enter email address';
my $timeout = 300;
my $cache_time = '7 days';
my $top_num = 10; 
my $json = JSON::MaybeXS->new->pretty;  # creates a json parsing object
my $uaheader = "Journal Distribution Compare Tool/beta (https://alhufton.com; mailto:$contact_email)";
my $alpha = 0.05; 
my $write_to_file = 0;

if ( $write_to_file ) {
    open( LOG, ">$tempdir_path/log.txt" );
}

# main parameter variables
my @issn_clean;
my @issn_unclean; # may include journal names
my $start_year;
my $end_year;
my $log = 0;
my $ignore_zero_citers = 0;
my $stepped = 0;
my $chart;
my $xmax = 'auto';

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
	
# Parse parameters, and create the content in the main lefthand column
opendiv("column-main");
if ( $q->param ) { 
	if ( clean_parameters($q) ) {
		make_results() if load_data();
	}
} else {
    # Define some defaults
    $log = 1; 
    $stepped = 1;
    $chart = 'ecdf';
	print_intro();
}
closediv();	# close main column

# Create righthand entry form
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
            my $issn = $_;
            $issn =~ s/\(.*?\)//g; 
            $issn =~ s/\s+//g; 
            my $issn_object = Business::ISSN->new($issn);
            if ( $issn_object && $issn_object->is_valid() ) { 
                push @issn_clean, $issn_object->as_string;
                push @issn_unclean, $_;
            } else { print "<p>WARNING: ISSN ($_) is invalid</p>"; }
        }
    }
    
    # Process the parameters
    $start_year = $form->param('start_year');
    $end_year = $start_year + $form->param('interval') - 1;
    
    if ( $form->param('log') ) { $log = 1 }   
    if ( $form->param('stepped') ) { $stepped = 1 } 
    if ( $form->param('zignore') ) { $ignore_zero_citers = 1 } 

    if ( $form->param('chart') && $form->param('chart') eq 'hist' ) { $chart = 'hist' }
    elsif ( $form->param('chart') && $form->param('chart') eq 'iecdf' ) { $chart = 'iecdf' }
    else { $chart = 'ecdf' }
    
    if ( $form->param('xmax') && $form->param('xmax') =~ /^[0-9]+$/ ) { $xmax = $form->param('xmax') }
    
    if ( $form->param('query') && $form->param('query') =~ /[a-zA-Z]+/ ) {
        get_ISSN_with_query( $form->param('query') ); return 0;
    }
    
    # Check for things that might prevent a full analysis run
    unless ( @issn_clean || $form->param('query') ) { print "<p>No valid ISSNs provided.</p>"; return 0; }
    unless ( $form->param('interval') <= $max_interval ) { print "<p>Selected interval exceeds maximum allowed.</p>"; return 0; }
    if ( @issn_clean > $max_journals ) { remove_journal(); return 0; }
    
    if ( $form->param('norun') ) { 
        print "<h2>Search for more journals, or hit the 'Go' button in the bottom right if you are ready to run the analysis &rarr;</h2>\n"; 
        return 0;
    }

    return 1; 
}

sub remove_journal {
    print "<h2>Too many journals selected. Please remove one.</h2>\n";
    foreach ( @issn_unclean ) {
        my $remove_url = $query_url;
        my $remove = $q->url_encode($_);
        $remove =~ s/\(/%28/g;
        $remove =~ s/\)/%29/g;
        $remove_url =~ s/&?ISSN=\Q$remove//;
        unless ( $remove_url =~ /&?norun=true/ ) { $remove_url .= "&norun=true"; }
        print "<p><a href=\"$remove_url\"><strong>Remove: </strong> $_</a></p>\n";
    }
}

sub get_ISSN_with_query {
    my $query = shift;
    my @titles;
    my %issns;
    
    my $ua = LWP::UserAgent->new;
    $ua->timeout(20);
    $ua->agent($uaheader);
    
    my $add_url = $query_url;
    $add_url =~ s/query=.*?(&|$)//;
    $query =~ s/^\s+|\s+$//g;
    $query = $q->url_encode($query);

    my $response = $ua->get("https://api.crossref.org/journals?query=$query&rows=400");
    if ($response->is_success) {
        my $metadata = decode_json $response->content;
        if ( @{$metadata->{'message'}->{'items'}} ) {
            foreach my $item ( @{$metadata->{'message'}->{'items'}} ) {
                push @titles, $item->{title};
                $issns{$item->{'title'}} = $item->{'ISSN'}->[0];
            }
        }
    } else { print "<p>Crossref search failed with message " . $response->status_line. "</p>"; return 0; }
    
    if ( @titles ) {
        @titles = sort { length $a <=> length $b } @titles;
        print "<h2>Journals found based on query: $query</h2>";
        
        for (0 .. 5) {
            if ( defined $titles[$_] && defined $issns{$titles[$_]} ) {
                my $insert = $q->url_encode( "$issns{$titles[$_]} ($titles[$_])" );
                print "<p><a href=\"$add_url&ISSN=$insert&norun=true\"><strong>Add</strong>: $issns{$titles[$_]} ($titles[$_])</a></p>";
            }
        }

    } else {
        print "<h2>No matching journals found with query: $query</h2>";
        return 0;
    }
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
    			unless ( $cache_results =~ /^Downloading/ ) { $fail = 1; }
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
			    # to add here: print the item to the log file, using the JSON pretty writer
			    if ( !defined $item->{'is-referenced-by-count'} || $item->{'is-referenced-by-count'} == 0 ) {
			        next if $ignore_zero_citers;
			        $item->{'is-referenced-by-count'} = 0;
			    }
			    $citation_counts{$issn}->add_data($item->{'is-referenced-by-count'});
			    
			    if ( $write_to_file ) {
			        print LOG "$issn\t$item->{'container-title'}->[0]\t$item->{'DOI'}\t$item->{'is-referenced-by-count'}\n";
			    }

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
    
    my %ecdf;  # hash of arrays. Always generated
    my %hist;  # hash of arrays. Only generated if chart = 'hist'
    my %iecdf; # hash of arrays. Only generated if chart = 'iecdf'
    my %n;
    my @results_HTML;
    my $j_num = scalar @issn_clean;
    
    # Place the distribution chart
    print "<div id=\"results\">\n";
    if ( $chart eq 'ecdf' ) {
        print "<h2>Empirical cumulative distribution function (eCDF)</h2>\n
        <p>Each point represents the fraction of papers (<em>y</em>) that 
        have <em>x</em> or fewer citations. Click on the journal names to toggle their display.</p>\n";
    } elsif ( $chart eq 'iecdf' ) {
        print "<h2>Inverse empirical cumulative distribution function (ieCDF)</h2>\n
        <p>Each point represents the fraction of papers (<em>y</em>) that 
        have <em>x</em> or more citations. Click on the journal names to toggle their display.</p>\n";
    } elsif ( $chart eq 'hist' ) {
        print "<h2>Normalized histogram</h2>\n
        <p>Each bar represents the fraction of papers (<em>y</em>) that 
        have exactly <em>x</em> citations. If a value was selected for 'x-axis max', the last bar 
        shows the proportion of papers with <em>x</em> or greater citations. Click on the journal names to toggle their display.</p>\n";
    } 
    print  "<canvas id=\"myChart\" aria-label=\"A chart showing the citation distributions of the selected journals\" role=\"img\"></canvas>\n";
        
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
        my $max = 0;
        
        foreach ( @uniqs ) {
            $i += $f->{$_}; 
            $ecdf{$issn}->[$_] = $i/$n{$issn}; 
            if ( $chart eq 'iecdf' ) {
                $iecdf{$issn}->[$_] = 1 - $i/$n{$issn};
            } elsif ( $chart eq 'hist') {
                $hist{$issn}->[$_] = $f->{$_}/$n{$issn};
            }
            $max = $_;
        }
        
        if ( $chart eq 'hist' ) {
            # Fill in bins with zero publications
            for (0 .. $max + 1) {
                $hist{$issn}->[$_] = 0 unless $hist{$issn}->[$_];
            }
            # Make final bar
            if ( $xmax ne 'auto' && $xmax < $max ) {
                my $k = 0;
                my $i = $xmax;
                until ($k) { 
                    $k = $ecdf{$issn}->[$i] if $ecdf{$issn}->[$i];
                    --$i;
                }
                $hist{$issn}->[$xmax] += 1 - $k;
                for (0 .. $max + 1) {
                    $hist{$issn}->[$_] = undef if ( $_ > $xmax + 1 );
                    $hist{$issn}->[$_] = 0 if ( $_ == $xmax + 1 ); 
                }
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
        $c_alpha /= 11 if ($j_num == 5);
        $c_alpha /= 16 if ($j_num == 6);
        
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
    
    # @issn_clean = sort { $citation_counts{$a}->median() <=> $citation_counts{$b}->median() } @issn_clean;
    
    if ( $chart eq 'hist' ) {
        drawChart (\%hist);
    } elsif ( $chart eq 'iecdf' ) {
        drawChart (\%iecdf);
    } else {
        drawChart (\%ecdf);
    }
    closediv();
}


# Writes a Chart.js javascript chart
sub drawChart {
    my %ecdf = %{$_[0]}; 
    
    # Set various formatting variables
    my $x_scale = 'linear';
    $x_scale = 'logarithmic' if $log;
    
    my $stepped_string = '';
    $stepped_string = "stepped: 'before'," if $stepped;
    
    my $x_min = 0;
    my $hist_callback = '';
    
    # If log is selected do some formatting to accommodate zero values (basically creating a symlog axis)
    if ( $log ) {
        $x_min = 0.9;
        # Mask out the = 0.9 label on the x-axis when log is selected. 
        $hist_callback = "ticks: { callback: function(value, index, values) { if ( value === $x_min ) return ''; else return value } },";
    }
    
    # If there is a xmax cutoff, we need to do some special formatting        
    my $xmax_string = '';
    if ( $xmax ne 'auto' ) {
        my $temp_max = $xmax;
        # For histograms with a cutoff we need to make some changes to accommodate the final bar
        if ( $chart eq 'hist' ) {
            # create some extra space
            $temp_max += int($xmax * 0.03) + 1; 
            # add a '>' sign to the tick label under the last bar, and mask the rest of the tick labels
            $hist_callback = "
            ticks: {
                callback: function(value, index, values) {
                  if ( value === $xmax )
                    return '>' + value;
                  else if ( value > $xmax || value === $x_min ) 
                    return '';
                  else 
                    return value;
                }
            },";
        }     
        $xmax_string = "max: $temp_max,"; 
    }
    
    # Axis labels
    my $xaxis_label = "Citations to paper since publication";
    my $yaxis_label = "Proportion with x or fewer citations";
    if ( $chart eq 'hist' ) {
        $yaxis_label = "Proportion with exactly x citations";
    } elsif ( $chart eq 'iecdf' ) {
        $yaxis_label = "Proportion with x or more citations";
    }
    
    # Define the colors that will be used for the data 
    my @bgcolors = chart_colors(0.5);
    my @bordercolors = chart_colors(0.9);
    
    # Create the data arrays
    my $data_string = '';
    my $k = 0; 
    foreach my $issn (@issn_clean) {
        
        # start a new data series
        $data_string .= "
        {  label: '$top_pubs{$issn}->[0]->{'container-title'}->[0]',
           showLine: 'true',
           backgroundColor: '$bgcolors[$k]',
           borderColor: '$bordercolors[$k]',
           data: [";

        ++$k;
            
        my $i = 0;
        my $max = $#{$ecdf{$issn}};
        foreach ( 0 .. $max ) {
            if ( defined $ecdf{$issn}->[$_] ) {
                my $y = sprintf("%.3f", $ecdf{$issn}->[$_]);
                $data_string .= "," if $i; ++$i; 
                $data_string .= "{x: $_, y: $y}";
            }
        }
        $data_string .= "]}, "; #closes data
    }
    
    ## print the Chart.js script ##
    print <<EOF;
<script>
Chart.defaults.color = "rgb(190,190,190)";
var ctx = document.getElementById('myChart').getContext('2d');
var myChart = new Chart(ctx, {
  type: 'scatter',
  data: {
      datasets: [$data_string]},

      options: {
        locale: 'en-US',
        aspectRatio: 1.7,
        layout: { padding: 10 },
        plugins: {
            tooltip: {
                mode: 'nearest'
            }, 
            legend: {
                display: true,
                labels: {
                    font: { size: 16 }
                }
            },
            filler: { drawTime: 'beforeDatasetsDraw' }
        },
        elements: { point: { hitRadius: 10, radius: 0 }, line: { $stepped_string fill: 'origin', tension: 0.4 } },
        scales: {
          x: {
             type: '$x_scale',
             position: 'bottom',
             $xmax_string
             $hist_callback
             min: $x_min, 
             title: {
                text: '$xaxis_label',
                display: 'true',
                font: { size: 16 }
             },
             grid: { 
                color: 'rgb(50,50,50)'
             }
          },
          y: {
             type: 'linear',
             position: 'left',
             suggestedMin: 0, 
             title: {
                text: '$yaxis_label',
                display: 'true',
                font: { size: 16 }
             },
             grid: { 
                color: 'rgb(50,50,50)'
             }
          }
        }
    }
});
</script>
EOF
}

sub chart_colors {
    my $transparency = shift; 
    return (
        "rgba(153,255,51,$transparency)",
        "rgba(0,51,204,$transparency)",
        "rgba(252,174,30,$transparency)",
        "rgba(190,0,220,$transparency)",
        "rgba(0,204,255,$transparency)",
        "rgba(255,255,0,$transparency)",
        );
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
    $cache->set($cache_id, 'Downloading (0%)', $max_download_time);
    
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
		my $total_result_num = 0;
		my $first = 1;
		my $next_cursor = '*';
		
		my @t = localtime;
		$t[5] += 1900;
		$t[4]++;
		my $iso_time = sprintf "%04d-%02d-%02d %02d:%02d:%02d", @t[5,4,3,2,1,0];
		print "Attempting to obtain citation data from CrossRef for ISSN $issn in year $year ($iso_time).\n";
	
		while ( $result_num > 0 || $first ) {
			my $rows; 
			my $response = $ua->get(
				"https://api.crossref.org/journals/$issn/works?filter=from-pub-date:$year,until-pub-date:$year,type:journal-article&rows=1000&select=DOI,title,is-referenced-by-count,container-title,short-container-title&cursor=$next_cursor"
				);
			if ($response->is_success) {
				my $metadata = decode_json $response->content;
				if ( $first ) {
					$first = 0;
					if ( $metadata->{'message'}->{'total-results'} ) { 
					    $result_num = $metadata->{'message'}->{'total-results'}; 
					    $total_result_num = $result_num;
					}
					if ( $result_num == 0 ) { print "WARNING: No results for $issn in $year.\n"; $cache->set($cache_id, "Failed (No results)", $timeout); exit; }
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
				$cache->set($cache_id, $fail_message, 20);
				exit;
			}
			$result_num -= 1000;
			
		    # Extend the cache marker if this will be a long run
		    if ( $result_num > 0) {
		        my $complete_percent = sprintf "%d", ( (1 - $result_num / $total_result_num) * 100);
		        $cache->set($cache_id, "Downloading ($complete_percent\%)", $max_download_time);
			}
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
    
    if ( $D > $Dcrit ) {
        return $D, 1;
    } else {
        return $D, 0;
    }
}

sub shuffle {
    my $deck = shift;     # $deck is a reference to an array
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
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.1.1/chart.min.js"></script>
<link rel="stylesheet" href="../css/tool.css">
</head>
<body onLoad="timeRefresh(5000);">
    
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
If a journal has more than one ISSN, the 'print' version is usually the one recognized 
by CrossRef. 500 errors may simply indicate a timeout problem due to a slow connection. 
Hit 'Go' again to retry.</p>
EOF

}


sub print_header {
    print "<div class=\"header\"><h1><a href=\"$tool_url\">Compare journal citation distributions <span style=\"color: red\"><em>beta</em></span></a></h1></div>\n";
}

sub print_tail {
    print <<EOF;  
<div class="footer">
<img style="float:left;display:inline;" src="https://assets.crossref.org/logo/metadata-from-crossref-logo-200.svg" width="200" height="68" alt="Metadata from Crossref logo">
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
    my @issn_rand = ('0098-7484', '2052-4463', '1548-7105', '1866-3516', 
        '1537-1719', '2046-1402', '1095-9203', '2054-5703', '2190-4286', 
        '1097-2765', '1759-4812', '0305-1048', '1944-8007', '1313-2970', 
        '1053-8119', '1368-4221', '1662-453X', '1687-0409', '1091-6490', '1744-4292');
    &shuffle(\@issn_rand);
    my $year_rand = 2015 + int rand(4);
    
    print <<EOF;
    
<div class="intro">
  <p>Compare the citation distributions of up to four journals using 
  open citation data from the <a href="https://github.com/CrossRef/rest-api-doc">CrossRef API</a>.</p>
  
  <p>The time interval controls which publications are considered 
  from the selected journals, but does not restrict when the citations occurred. For example, if you select 
  2015 and a two-year interval, then papers published in 2015 and 2016 are 
  included, but all citations from any time after publication will be counted 
  (i.e. the citing works could be published anytime from 2015 to present).</p>
  
  <p>Please note that it could take up to several minutes for the results to be 
  generated, especially if you are comparing journals with thousands of 
  publications per year.</p> 
  
  <p>The hypotheses that the distributions are distinct are evaluated using pairwise 
  <a href="https://en.wikipedia.org/wiki/Kolmogorov-Smirnov_test">Kolmogorov-Smirnov 
  tests</a>.</p> 
  
  <p>Try a <a href="$tool_url?ISSN=$issn_rand[0]&ISSN=$issn_rand[1]&ISSN=$issn_rand[2]&ISSN=$issn_rand[3]&start_year=$year_rand&interval=1&log=true&stepped=true">Random Example</a>!</p>
  
  <p><a href="https://github.com/alhufton2/journal-dist-compare">Source code and methods&nbsp;▸</a></p>
  
</div>

EOF

}

sub print_prompt {
    
    my @issn_value;
    my $default_year = 2000;
    if ( $start_year ) { $default_year = $start_year;} 
    my $log_checked = " checked=\"true\"" if ( $log );
    my $stepped_checked = " checked=\"true\"" if ( $stepped );
    my $zignore_checked = " checked=\"true\"" if ( $ignore_zero_citers );
    my $ecdf_checked = " selected=\"selected\"" if ( $chart eq 'ecdf' );
    my $hist_checked = " selected=\"selected\"" if ( $chart eq 'hist' );
    my $iecdf_checked = " selected=\"selected\"" if ( $chart eq 'iecdf' );
    
    for ( 0..3 ) { $issn_value[$_] = '' }
    my $i = 0;
    if ( @issn_unclean ) { 
        foreach ( @issn_unclean ) {
            if ( defined $top_pubs{$_}->[0]->{'container-title'}->[0] ) {                
                $issn_value[$i] = "$_ ($top_pubs{$_}->[0]->{'container-title'}->[0])";
            } else {
                $issn_value[$i] = $_;
            }
            ++$i;       
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
  <h3><label for="query">Find journals</label>&nbsp;<span class="tooltip">?<span class="tooltiptext tooltip-left">
  Enter the full journal title, not an abbreviation
  </span></span></h3>
  <input id="query" type="text" name="query" size="15" maxlength="50"><input type="submit" value="Search"></p>

  <h3>Selected journals&nbsp;<span class="tooltip">?<span class="tooltiptext tooltip-left">
     The journal ISSNs listed below will be included in the analysis. Delete an ISSN and hit 'Go' again to remove it.
  </span></span></h3>
  <label for="ISSN">Enter <a href="https://portal.issn.org/">ISSNs</a> directly or select via the journal search box above</label>
  <p><input id="ISSN" type="text" name="ISSN" size="17" maxlength="50" value="$issn_value[0]">
    <input id="ISSN" type="text" name="ISSN" size="17" maxlength="50" value="$issn_value[1]">
    <input id="ISSN" type="text" name="ISSN" size="17" maxlength="50" value="$issn_value[2]">
    <input id="ISSN" type="text" name="ISSN" size="17" maxlength="50" value="$issn_value[3]"></p>

  <h3>Publication years&nbsp;<span class="tooltip">?<span class="tooltiptext tooltip-left">
     Select which years' content you want to analyze from the selected journals. 
  </span></span></h3>
  <p><label for="year">start year</label>&nbsp;<select id="year" name="start_year" required="true"></select></br>
  <label for="interval">interval (yrs)</label>&nbsp;<select id="interval" name="interval">$interval_opt</select></br></p>
  <h3>Display options</h3>
  <p><label for="chart">Chart&nbsp;</label>
  <select id="chart" name="chart">
  <option $ecdf_checked value="ecdf">eCDF</option>
  <option $iecdf_checked value="iecdf">inv eCDF</option>
  <option $hist_checked value="hist">histogram</option>
  </select>
  <span class="tooltip">?<span class="tooltiptext tooltip-left">
     Select the chart type: empirical cumulative distribution function (eCDF), inverse eCDF, or a normalized histogram
  </span></span><br>
  <label for="xmax">x-axis&nbsp;</label><input type="text" name="xmax" size="1" maxlength="50" value="$xmax">
  <span class="tooltip">?<span class="tooltiptext tooltip-left">
     Enter a positive integer to set a cutoff for the x-axis. If no number is entered, the range will be automatically set to show the full distributions.
  </span></span></p>
  <p><input style="display:inline" type="checkbox" id="log" name="log" value="true"$log_checked>
  <label for="log">logarithmic</label>
  <span class="tooltip">?<span class="tooltiptext tooltip-left">
     Plot the axis in log10 space. 
  </span></span><br>
  <input style="display:inline" type="checkbox" id="zignore" name="zignore" value="true"$zignore_checked>
  <label for="zignore">ignore no-citers</label>
  <span class="tooltip">?<span class="tooltiptext tooltip-left">  
     Remove all publications with zero citations from the dataset.
  </span></span><br>
  <input style="display:inline" type="checkbox" id="stepped" name="stepped" value="true"$stepped_checked>
  <label for="stepped">stepped line&nbsp;</label>
  <span class="tooltip">?<span class="tooltiptext tooltip-left">  
     If selected, a stepped line (eCDF & inverse eCDF) or squared bars (histogram) are shown. If unselected, a curve is drawn through the points.
  </span></span></p>
  
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
<div class="nav"><p><a href="https://alhufton.com">home</a> &#9657; <a href="https://alhufton.com/tools/">tools</a> &#9657; <a href=\"$tool_url\">journal compare tool</a></p></div>
EOF
}

  