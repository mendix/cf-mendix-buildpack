#
# This function, format_dict_table was copied from the DendroPy Phylogenetic
# Computing Library version 3.7.1, from the file dendropy/utility/textutils.py
#
#  Copyright 2010 Jeet Sukumaran and Mark T. Holder.
#  All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are met:
#
#      * Redistributions of source code must retain the above copyright
#        notice, this list of conditions and the following disclaimer.
#
#      * Redistributions in binary form must reproduce the above copyright
#        notice, this list of conditions and the following disclaimer in the
#        documentation and/or other materials provided with the distribution.
#
#      * The names of its contributors may not be used to endorse or promote
#        products derived from this software without specific prior written
#        permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
#  IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL JEET SUKUMARAN OR MARK T. HOLDER
#  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
#  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
#  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
#  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.
#
#  If you use this work or any portion thereof in published work,
#  please cite it as:
#
#     Sukumaran, J. and M. T. Holder. 2010. DendroPy: a Python library
#     for phylogenetic computing. Bioinformatics 26: 1569-1571.


def format_dict_table(
    rows, column_names=None, max_column_width=None, border_style=2
):
    """
    Returns a string representation of a tuple of dictionaries in a
    table format. This method can read the column names directly off the
    dictionary keys, but if a tuple of these keys is provided in the
    'column_names' variable, then the order of column_names will follow
    the order of the fields/keys in that variable.
    """
    if column_names or len(rows) > 0:
        lengths = {}
        rules = {}
        if column_names:
            column_list = column_names
        else:
            try:
                column_list = list(rows[0].keys())
            except Exception:
                column_list = None
        if column_list:
            # characters that make up the table rules
            border_style = int(border_style)
            # border_style = 0
            if border_style == 0:
                vertical_rule = "  "
                horizontal_rule = ""
                rule_junction = ""
            elif border_style == 1:
                vertical_rule = " "
                horizontal_rule = "-"
                rule_junction = "-"
            else:
                vertical_rule = " | "
                horizontal_rule = "-"
                rule_junction = "-+-"
            if border_style >= 3:
                left_table_edge_rule = "| "
                right_table_edge_rule = " |"
                left_table_edge_rule_junction = "+-"
                right_table_edge_rule_junction = "-+"
            else:
                left_table_edge_rule = ""
                right_table_edge_rule = ""
                left_table_edge_rule_junction = ""
                right_table_edge_rule_junction = ""

            if max_column_width:
                column_list = [c[:max_column_width] for c in column_list]
                trunc_rows = []
                for row in rows:
                    new_row = {}
                    for k in row.keys():
                        new_row[k[:max_column_width]] = str(row[k])[
                            :max_column_width
                        ]
                    trunc_rows.append(new_row)
                rows = trunc_rows

            for col in column_list:
                rls = [len(str(row[col])) for row in rows]
                lengths[col] = max(rls + [len(col)])
                rules[col] = horizontal_rule * lengths[col]

            template_elements = [
                "%%(%s)-%ss" % (col, lengths[col]) for col in column_list
            ]
            row_template = vertical_rule.join(template_elements)
            border_template = rule_junction.join(template_elements)
            full_line = (
                left_table_edge_rule_junction
                + (border_template % rules)
                + right_table_edge_rule_junction
            )
            display = []
            if border_style > 0:
                display.append(full_line)
            display.append(
                left_table_edge_rule
                + (row_template % dict(zip(column_list, column_list)))
                + right_table_edge_rule
            )
            if border_style > 0:
                display.append(full_line)
            for row in rows:
                display.append(
                    left_table_edge_rule
                    + (row_template % row)
                    + right_table_edge_rule
                )
            if border_style > 0:
                display.append(full_line)
            return "\n".join(display)
        else:
            return ""
    else:
        return ""
