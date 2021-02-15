#!/usr/bin/perl

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

# Read in any CGI parameters and clean whitespace
my $tool_url = $q->url();

# Open the cache
my $tempdir_path = 'path/to/temp/dir';
my $cache = CHI->new( driver => 'File', root_dir => $tempdir_path );

# Set various variables
my $max_interval = 3; # maximum year interval allowed. 
my $contact_email = 'enter your email address';
my $timeout = 300;
my $cache_time = '7 days';
my $top_num = 10; 
my $json = JSON::MaybeXS->new->pretty;  # creates a json parsing object
my $uaheader = "Journal Distribution Compare Tool/beta (https://alhufton.com; mailto:$contact_email)";
my $alpha = 0.05; 

binmode(STDOUT, ":utf8");

# main parameter variables
my @issn_clean;
my $start_year;
my $end_year;
my $log;

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
opendiv("column main");
my $error = 0;
if ( $q->param ) { 
	if ( clean_parameters($q) ) {
		make_results() if load_data();
	} else { $error = 1; }
} elsif ( $error == 0 ) {
	print_intro();
}
closediv();	# close main column

# Create lefthand entry form
opendiv("column side");
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
    	
    return 1; 
}

# Load data from the cache into the main variables
sub load_data { 
	
    my $status_table = new HTML::Table( -head=>['ISSN', 'Year', 'Status'] );	
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
    
    my %ecdf; # hash of arrays
    my %n;
    my @results_HTML;
    my $j_num = scalar @issn_clean;
    
    # Place the distribution chart
    print "<div id=\"results\">\n";
    print "<h2>Empirical cumulative distribution plots</h2>\n";
    print  "<canvas id=\"myChart\"></canvas>\n";
    
    # output some basic summary stats
    print "<h2>Summary statistics</h2>\n";
    print "<p>for journal articles published in $start_year";
    if ($end_year == $start_year) { print "</p>\n"; }
    else { print " to $end_year</p>\n"; }
    my $stattable = new HTML::Table( -head=>['Journal', 'ISSN', 'Count', 'Mean', 'Median', 'Variance'] );
    $stattable->setRowHead(1);
   
    foreach my $issn ( @issn_clean ) {
        $n{$issn} = $citation_counts{$issn}->count();
        my @uniqs = $citation_counts{$issn}->uniq(); 
        my $f = $citation_counts{$issn}->frequency_distribution_ref(\@uniqs);
        my $i = 0;
        foreach ( @uniqs ) {
            $i += $f->{$_};
            $ecdf{$issn}->[$_] = $i/$n{$issn};
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
        my $pairtable = new HTML::Table( -width=>'70%', -data=>[['', @short_journal_names]] );
        
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
                    $cell_content = 0;
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
    print "<p>citation counts in parentheses</p>\n";
    foreach my $issn ( @issn_clean ) {
        print "<h3>$top_pubs{$issn}->[0]->{'container-title'}->[0]</h3>\n";
        print "<ol>\n";
        foreach ( @{$top_pubs{$issn}} ) {
            my $doi = $_->{'DOI'};
            my $title = $_->{'title'}->[0];
            my $is_ref_by = $_->{'is-referenced-by-count'};
            print "<li><a href=\"https://doi.org/$doi\">$title</a> ($is_ref_by)</li>\n";
        }
        print "</ol>\n";
    }
    
    drawChart (\%ecdf);  
    closediv();
}


# Writes a Chart.js javascript with cumulative distribution plots
sub drawChart {
    my %ecdf = %{$_[0]}; 
    my $x_scale;
    if ($log) { $x_scale = 'logarithmic' }
    else { $x_scale = 'linear' }
    
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
        print <<EOF;
        {
           label: '$top_pubs{$issn}->[0]->{'container-title'}->[0]',
           steppedLine: 'after',
           showLine: 'true',
           backgroundColor: "$bgcolors[$k]",
           data: [
EOF
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
                labelString: 'Citations to paper since publication (log10)',
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
                labelString: 'Cumulative probability',
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


############################
# HTML writing subroutines #
############################

# Collapsible text box based on https://alligator.io/css/collapsible/

sub start_html {
    print <<EOF;

<head>
<title>Compare Journal Citation Distributions</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/2.9.4/Chart.min.js"></script>
<style>
* {
  box-sizing: border-box;
}

body {
  font-family: Verdana, Geneva, sans-serif;
  color: #999;
  font-size: .9rem;
  background-color: black;
  max-width: 1000px;
  margin: auto;
  width: 100vw;
  padding: 10px;

}

a, a:visited {
  color: white;
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

pre {
  white-space: pre-wrap
}

table {
  border-collapse: collapse;
  margin-top: 5px;
  margin-bottom: 10px;
}

table, th, td {
  border: 1px solid white;
  font-family: Verdana, Geneva, sans-serif;
  color: #999;
  font-size: .9rem;
  padding: 5px;
}

/* Style the header */
.header {
  font-family: Arial, Helvetica, sans-serif;
  padding: 5px;
  text-align: left;
  font-size: 1.1rem;
}

.header a {
  text-decoration: none;
  color: rgb(238, 238, 238);
}

/* Style the intro */
.intro {
  padding: 10px;
  text-align: justify;
}

.results h3, .results h2, .results h4 {
  color: #70db70;
  font-weight: normal;
}

.button {
  padding: 10px;
}

.flip {
  font-size: 16px;
  padding: 7px;
  text-align: center;
  background-color: darkgrey;
  color: white;
  border: solid 1px #a6d8a8;
  margin: auto;
  width: 50%;
  margin-bottom: 1rem; 
}

.flip:hover {
  color: #66ff66;
  cursor: pointer; 
}


/* Create three equal columns that floats next to each other */
.row {
  border-top: 0.5px solid;
  border-top-color: rgb(68,68,68);
}

.column {
  float: left;
}

.column.side {
  width: 20\%;
  padding: 5px;
}

.column.main {
  width: 80\%;
  padding: 5px;
}

.column h2, h3, h4 {
  margin-top: 0; 
  color: #70db70;
  font-weight: normal;
}

/* Clear floats after the columns */
.row:after {
  content: "";
  display: table;
  clear: both;
}

/* Style the footer */
.footer {
  padding: 10px;
  text-align: right;
  border-top: 1px solid;
  border-top-color: rgb(68,68,68);
}

/* Style the breadcrumbs nav */
.nav {
  border-top: 1px solid;
  border-top-color: rgb(68,68,68);
}

/* Responsive layout - makes the three columns stack on top of each other instead of next to each other */
\@media screen and (max-width: 600px) {
  .column.main, .column.side {
    width: 100\%;
  }
}

</style>

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
</div>

EOF

}

sub print_prompt {
    
    my @issn_value;
    my $default_year = 2000;
    if ( $start_year ) { $default_year = $start_year;} 
    
    foreach (0..3) {
        unless ( defined $issn_clean[$_] ) {
            $issn_value[$_] = "";
        } else {
            $issn_value[$_] = $issn_clean[$_];
        }
    }
    
    my $interval_opt ='';
    foreach (0..$max_interval) {
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
  <label for="log">logarithmic&nbsp;</label>
  <input style="display:inline" type="checkbox" id="log" name="log" value="true" checked="true"></p>
  
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