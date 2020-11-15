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
use Statistics::Discrete;
use Statistics::ANOVA;
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
my $contact_email = 'enter your email address';
my $timeout = 60;
my $cache_time = '7 days';
my $top_num = 10; 
my $json = JSON::MaybeXS->new->pretty;  # creates a json parsing object
my $uaheader = "Journal Distribution Compare Tool/alpha (https://alhufton.com, mailto:$contact_email)";

binmode(STDOUT, ":utf8");

# main parameter variables
my @issn_clean;
my $start_year;
my $end_year;
my $log; 

# main data variables
my %journal_dois;    #array per ISSN, top ten guaranteed to be sorted
my %journal_names;   #per ISSN
my %citation_counts; #per doi
my %titles;          #per doi

# Main body 
# Let's create a separate subroutine just to clean and check the parameters. 
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
        if ( @results ) {
            my $num = @results;
            foreach my $item ( @results ) {
                if ( $item->{'is-referenced-by-count'} ) {
                    $citation_counts{$item->{'DOI'}} = $item->{'is-referenced-by-count'};
 
                    ### partial sorting algorithm ######
                    my $k = 0;
                    my $added = 0;
                    foreach my $doi ( @{$journal_dois{$_}} ) {
                        last if ( $k > $top_num );
                        if ( $item->{'is-referenced-by-count'} >= $citation_counts{$doi} ) {
                            splice @{journal_dois{$_}}, $k, 0, $item->{'DOI'};
                            $added = 1;
                            last;
                        }
                        ++$k;
                    }
                    if ( $added == 0 ) { push @{$journal_dois{$_}}, $item->{'DOI'} }
                    ####################################          
                    
                } else {
                    $citation_counts{$item->{'DOI'}} = 0;
                    push @{$journal_dois{$_}}, $item->{'DOI'};
                }
                
                $titles{$item->{'DOI'}} = $item->{'title'}->[0];
                unless ( $journal_names{$_} ) {
                    $journal_names{$_}->{'container-title'} = $item->{'container-title'}->[0];
                    if ( $item->{'short-container-title'}->[0] ) {
                        $journal_names{$_}->{'short-container-title'} = $item->{'short-container-title'}->[0]; 
                    } else {
                        $journal_names{$_}->{'short-container-title'} = $item->{'container-title'}->[0];
                    }
                }
            }
        }
    }
    
    print "Running calculations\n";
    print "</pre></div>\n";
    $| = 0;    
    print "<p class=\"flip\" id=\"results_button\" onclick=\"toggleRes()\">Show Results</p>\n";
}

sub make_results {
    
    my %cdfs;
    
    # Place the distribution chart
    print "<div id=\"results\">\n";
    print "<h2>Empirical cumulative distribution plots</h2>\n";
    print "<canvas id=\"myChart\"></canvas>\n";
    
    # output some basic summary stats
    my $aov = Statistics::ANOVA->new();
    my $k = 1;
    print "<h2>Summary statistics</h2>\n";
    print "<p>for journal articles published in $start_year";
    if ($end_year == $start_year) { print "</p>\n"; }
    else { print " to $end_year</p>\n"; }
    my $stattable = new HTML::Table( -head=>['Journal', 'ISSN', 'Count', 'Mean', 'Median', 'Variance'] );
    $stattable->setRowHead(1);
   
    foreach my $issn ( @issn_clean ) {
        if ( $journal_dois{$issn} ) {
            my $stat = Statistics::Discrete->new();
            my @citations = map { $citation_counts{$_} } @{$journal_dois{$issn}}; 
            $stat->add_data(@citations);
            
            $cdfs{$issn} = $stat->empirical_distribution_function();
            
            $stattable->addRow(
                $journal_names{$issn}->{'container-title'}, 
                $issn, 
                $stat->count(), 
                sprintf("%.2f", $stat->mean()), 
                $stat->median(), 
                sprintf("%.2f", $stat->variance())
                );
            
            $aov->add_data($k => @citations);
            ++$k;
        }
    }
    $stattable->print;
   
    if ( $k > 1 ) {
        
        # Independent nominal variables (groups) ANOVA - NON-parametric
        print_KW_intro();
        
        my %res = $aov->anova(independent => 1, parametric => 0);
        print "<h4>Kruskal-Wallis</h4>\n";
        my $kwtable = new HTML::Table( 
            -head=> ['H', 'p-value'], 
            -data=> [[sprintf("%.4g",$res{h_value}), sprintf("%.4g", $res{p_value})]] 
            );
        $kwtable->print;
        
        # Run pairwise
        if ( $res{'p_value'} <= 0.05 ) {
            print "<h4>Pairwise tests</h4>\n";
            my @short_journal_names = map { $journal_names{$_}->{'short-container-title'} } @issn_clean;
            my $pair_result = $aov->compare(independent => 1, parametric => 0, tails => 2, flag => 1, alpha => .05, dump => 0);
            my $pairtable = new HTML::Table( -width=>'70%', -data=>[['', @short_journal_names]] );
            my $k = 1;
            my $col_width = 100/(@issn_clean+1);
            foreach (@issn_clean) {
                my $i = 1;
                my $r = $k + 1;
                my $jname = shift @short_journal_names;
                $pairtable->setCell($r,1,$jname);
                foreach (@issn_clean) {
                    my $c = $i + 1;
                    if ( $k == 1) { $pairtable->setColWidth($c, "$col_width\%") }
                    
                    my $z_value = 0;
                    my $flag = 0;
                    if ( $i == $k ) {
                        $pairtable->setCell($r,$c,'-');
                    } elsif ( $k < $i ) { 
                        $flag = $pair_result->{"$k,$i"}->{'flag'};
                        $z_value = abs($pair_result->{"$k,$i"}->{'z_value'});
                    } elsif ( $i < $k ) {
                        $flag = $pair_result->{"$i,$k"}->{'flag'};
                        $z_value = abs($pair_result->{"$i,$k"}->{'z_value'});
                    }
                    my $cell_content = sprintf("%.4g", $z_value);
                    $cell_content .= '*' if ( $flag );
                    $pairtable->setCell($r,$c,$cell_content);
                    
                    # set cell color
                    my $hue = $z_value*25;
                    $hue = 255 if ($hue > 255);
                    my $text_hue = 0;
                    if ( $hue < 150 ) { $text_hue = 255 }
                    if ( $hue < 50 )  { $text_hue = 153 }
                    my $color_bias = $hue * 0.75;
                    $pairtable->setCellStyle($r, $c, "color: rgb($text_hue,$text_hue,$text_hue); background-color: rgb($hue,$color_bias,$hue)");
                    ++$i;
                }
                ++$k;
            }
            $pairtable->print; 
            print "<p>Z values for the pairwise tests are shown (the higher the number, the more different are the journal's citation distributions). An '*' indicates that the difference is significant after Bonferroni correction at an alpha value of 0.05.</p>";
        }
    }
    
    # Create top ten lists
    print "<h2>Top $top_num cited papers for each journal</h2>\n";
    print "<p>citation counts in parentheses</p>\n";
    foreach ( @issn_clean ) {
        print "<h3>$journal_names{$_}->{'container-title'}</h3>\n";
        print "<ol>\n";
        for my $k ( 0..9 ) {
            my $doi = $journal_dois{$_}->[$k];
            print "<li><a href=\"https://doi.org/$doi\">$titles{$doi}</a> ($citation_counts{$doi})</li>\n";
        }
        print "</ol>\n";
    }
    
    drawChart (\%cdfs);  
    print "</div>\n";
    print "<p class=\"flip\" id=\"status_button\" onclick=\"toggleSta()\">Show Status</p>\n";
}


# Writes a Chart.js javascript with cumulative distribution plots
sub drawChart {
    my %cdfs = %{$_[0]}; 
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
    foreach (keys %cdfs) {
        my $issn = $_;

        my @cite_nums_sorted = sort { $a <=> $b } (keys %{$cdfs{$issn}});
        print "," if $k;
        
####### start a new data series
        print <<EOF;
        {
           label: '$journal_names{$issn}->{'container-title'}',
           steppedLine: 'after',
           showLine: 'true',
           backgroundColor: "$bgcolors[$k]",
           data: [
EOF
##############################
        ++$k;
            
        my $i = 0;
        foreach (@cite_nums_sorted) {
            print "," if $i; ++$i; 
            print "             {x: $_, y: $cdfs{$issn}->{$_}}";
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
    $ua->agent("$uaheader"); 
    
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
    for(var year = start ; year <end; year++){ 
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

sub print_KW_intro {
    
    print <<EOF;
<h3>Non-parametric ANOVA</h3>
<p>The <a href="https://en.wikipedia.org/wiki/Kruskal-Wallis_one-way_analysis_of_variance">Kruskal Wallis H test</a> 
is used to determine whether there are significant differences in the citation distributions. Pairwise Mann-Whitney 
U tests are then conducted, if justified, by the Steel-Dwass procedure.</p>

EOF
       
}

sub print_menu {
    print <<EOF;
<div class="nav"><p><a href="https://alhufton.com">home</a> &#9657; tools &#9657; journal compare tool</p></div>
EOF
}