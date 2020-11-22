#!/opt/local/bin/perl

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

# Load other packages
use CHI; 
use Encode;
use Statistics::Descriptive::Discrete;
use HTML::Table;
use Business::ISSN;
use LWP::UserAgent;
use JSON::MaybeXS;
use open qw( :encoding(UTF-8) :std );

# Read in any CGI parameters and clean whitespace
my $tool_url = $q->url();

# Open the cache
my $cache = CHI->new( driver => 'File' );
# my $cache = CHI->new( driver => 'File', root_dir => '/home3/alhufton/tmp/journal-compare' );

# Set various variables
my $max_interval = 3; # maximum year interval allowed. 
my $contact_email = 'enter email here';
my $timeout = 60;
my $cache_time = '7 days';
my $top_num = 10; 
my $json = JSON::MaybeXS->new->pretty;  # creates a json parsing object
my $uaheader = "Journal Distribution Compare Tool/alpha (https://alhufton.com, mailto:$contact_email)";
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
print "Content-Type: text/html; charset=utf-8\n\n";
start_html();
print_header();
print_menu();
opendiv("row");
if ( $q->param && clean_parameters($q) ) { #fills @issn_clean, $start_year, $end_year
    opendiv("column side");
    print_prompt();
    closediv(); # close column side
    
    opendiv("column main");
    get_data();
    make_results();
    closediv(); # close column main
} else {
    opendiv("column side");
    print_prompt();
    closediv(); # close column side
    
    opendiv("column main");
    print_intro();
    closediv(); # close column main
}
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
    
sub get_data {     
    # force a print flush, so that user sees a more complete html page while waiting for work to finish
    $| = 1; 
    
    print "<div id=\"status\">\n";
    print "<pre>\n";
    print "Compiling citation data. This could take up to several minutes.\n";
    
    foreach ( @issn_clean ) {
        print "Obtaining citation metadata for journal $_.\n";
        my @results = get_crossref_metadata($_, $start_year, $end_year, $uaheader);
        print "Processing metadata for journal $_.\n";
        if ( @results ) {
            
            $citation_counts{$_} = new Statistics::Descriptive::Discrete;
            
            my $min;
            foreach my $item ( @results ) {
                if ( $item->{'is-referenced-by-count'} ) {
                   $citation_counts{$_}->add_data($item->{'is-referenced-by-count'});
 
                    ### partial sorting algorithm ######
                    my $k = 0;
                    my $added = 0;
                    if ( ! defined $min || $item->{'is-referenced-by-count'} > $min ) {
                        foreach my $item2 ( @{$top_pubs{$_}} ) {
                            last if ( $k > $top_num );
                            if ( $item->{'is-referenced-by-count'} >= $item2->{'is-referenced-by-count'} ) {
                                splice @{$top_pubs{$_}}, $k, 0, $item;
                                pop @{$top_pubs{$_}} if ( @{$top_pubs{$_}} > $top_num ); 
                                $min = $item->{'is-referenced-by-count'} if ( $item->{'is-referenced-by-count'} < $min );
                                $added = 1;
                                last;
                            }
                            ++$k;
                        }
                    }
                    if ( $added == 0 && @{$top_pubs{$_}} < $top_num ) { 
                        push @{$top_pubs{$_}}, $item;
                    }
                    
                    ####################################          
                    
                } else {
                    $citation_counts{$_}->add_data(0);
                }
            }
        } else { die "No items in CrossREF result for $_\n\n"; }
    }
    
    print "Running calculations\n";  
}

sub make_results {
    
    my %ecdf; # hash of arrays
    my %n;
    my @results_HTML;
    my $j_num = scalar @issn_clean;
    
    push @results_HTML, "<p class=\"flip\" id=\"results_button\" onclick=\"toggleRes()\">Show Results</p>\n";

    # Place the distribution chart
    push @results_HTML, "<div id=\"results\">\n";
    push @results_HTML, "<h2>Empirical cumulative distribution plots</h2>\n";
    push @results_HTML,  "<canvas id=\"myChart\"></canvas>\n";
    
    # output some basic summary stats
    push @results_HTML, "<h2>Summary statistics</h2>\n";
    push @results_HTML, "<p>for journal articles published in $start_year";
    if ($end_year == $start_year) { push @results_HTML, "</p>\n"; }
    else { push @results_HTML, " to $end_year</p>\n"; }
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
    push @results_HTML, $stattable->getTable();
   
    if ( $j_num > 1 ) {
        
        # Running the Kolmogorov-Smirnov pairwise tests
        push @results_HTML, "<h3>Kolmogorov-Smirnov tests</h3>\n";
        print "Running pairwise KS tests.\n";
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
        push @results_HTML, $pairtable->getTable(); 
        push @results_HTML, "<p>D values for the pairwise tests are shown (the higher the number, the more different are the journals' citation distributions). An '*' indicates that the difference is significant after Bonferroni correction at an alpha value of $alpha.</p>";
    }
    print "</pre></div>\n"; # Here I am closing the status section. This is not ideal since I am generating a div across two subroutines...
    $| = 0;  
    
    foreach ( @results_HTML ) { print $_; } 
    
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
    print "</div>\n";
    print "<p class=\"flip\" id=\"status_button\" onclick=\"toggleSta()\">Show Status</p>\n";
}


# Writes a Chart.js javascript with cumulative distribution plots
sub drawChart {
    my %ecdf = %{$_[0]}; 
    my $x_scale;
    if ($log) { $x_scale = 'logarithmic' }
    else { $x_scale = 'linear' }
    
    # Define the colors that will be used for the four data series
    my @bgcolors = (
        "rgba(153,255,51,0.4)",
        "rgba(234,162,33,0.4)",
        "rgba(0,220,153,0.4)",
        "rgba(190,0,220,0.4)",
        );
    
###### start the Chart.js script #
    print <<EOF;
<script>    
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
             }
          }],
          yAxes: [{
             type: 'linear',
             position: 'left',
             scaleLabel: {
                labelString: 'Cumulative probability',
                display: 'true',
                fontSize: 16
             }
          }]
        }
    }
});
</script>
EOF
#############################
}


# a valid ISSN, start year and end year
sub get_crossref_metadata {
    my $issn = shift;
    my $start = shift;
    my $end = shift;
    my $uaheader = shift;
    my @results; # array of hashes with {title, doi, is-referenced-by-count} 
    
    my $ua = LWP::UserAgent->new;
    $ua->timeout($timeout);
    $ua->agent($uaheader); 
    
    foreach ($start .. $end) {
        my $year = $_; 
    
        my $result_num = 0;
        my $first = 1;   
        my $offset = 0;
        
        my $cache_id = "$year-$issn";
        
        my $cache_results = $cache->get($cache_id);
        if ( defined $cache_results ) {
            push @results, @$cache_results;
            print "Using cached data for year $year\n";
            next;
        }
        
        my @temp_results;
        
        while ( $result_num > 0 || $first ) {
            my $rows; 
            print "Requesting data from CrossRef for year $year (offset: $offset)\n";
            my $response = $ua->get(
                "https://api.crossref.org/journals/$issn/works?filter=from-pub-date:$year,until-pub-date:$year,type:journal-article&rows=1000&offset=$offset&select=DOI,title,is-referenced-by-count,container-title,short-container-title"
                );
            if ($response->is_success) {
                my $metadata = decode_json $response->content;
                if ( $first ) {
                    $first = 0;
                    if ( $metadata->{'message'}->{'total-results'} ) { $result_num = $metadata->{'message'}->{'total-results'}; }
                    if ( $result_num == 0 ) { return; }
                    if ( $result_num >= 10000 ) { print "<p>WARNING: More than 10000 items found for $issn in $year. Skipping it.</p>\n"; return; }
                }
                if ( @{$metadata->{'message'}->{'items'}} ) {
                    foreach my $item ( @{$metadata->{'message'}->{'items'}} ) {
                        push @temp_results, $item;
                    }
                }
            } else {
                print "<p>WARNING: CrossRef call failed for $issn. ";
                print "Journals may have more than one ISSN, and may not register all with CrossRef.";
                print " (" . $response->status_line . "). </p>"; 
                return;
            }
            $offset += 1000;
            $result_num -= 1000;
        }
        $cache->set($cache_id, \@temp_results, $cache_time);
        push @results, @temp_results;
    }
    return @results;
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
  color: #ffbe61;
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

#results, #status_button {
  display: none;
}

</style>

<script>
function toggleRes() {
    document.getElementById("results").style.display = "block";
    document.getElementById("status").style.display = "none";
    document.getElementById("status_button").style.display = "block";
    document.getElementById("results_button").style.display = "none";
}
</script>

<script>
function toggleSta() {
    document.getElementById("results").style.display = "none";
    document.getElementById("status").style.display = "block";
    document.getElementById("results_button").style.display = "block";
    document.getElementById("status_button").style.display = "none";
}
</script>

</head>
<body>
    
EOF

}

sub opendiv {
    my $class = shift;
    print "<div class=\"$class\">\n";
}

sub closediv {
    print "</div>\n";
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
<div class="nav"><p><a href="https://alhufton.com">home</a> &#9657; tools &#9657; journal compare tool</p></div>
EOF
}