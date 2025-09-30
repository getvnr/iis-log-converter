import streamlit as st
import pandas as pd
from io import BytesIO
import altair as alt  # For advanced charts
import re

# Ensure openpyxl is available
try:
    import openpyxl
except ImportError:
    st.error("The 'openpyxl' library is not installed. Please ensure it is included in your environment (e.g., via requirements.txt).")
    st.stop()

def parse_iis_log(file_content):
    try:
        lines = file_content.decode('utf-8', errors='ignore').splitlines()
        fields = None
        data = []
        
        for line in lines:
            if line.startswith('#'):
                if line.startswith('#Fields:'):
                    fields = line.split()[1:]
                continue
            if fields and line.strip():
                row = line.split()
                if len(row) == len(fields):
                    data.append(row)
        
        if not fields or not data:
            raise ValueError("Invalid IIS log format or no data found")
        
        df = pd.DataFrame(data, columns=fields)
        
        # Convert relevant columns to numeric
        numeric_cols = ['s-port', 'sc-status', 'sc-substatus', 'sc-win32-status', 'sc-bytes', 'cs-bytes', 'time-taken']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Combine date and time into datetime if present
        if 'date' in df.columns and 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], errors='coerce')
        
        return df
    except Exception as e:
        raise ValueError(f"Error parsing log file: {str(e)}")

def generate_summary(df):
    try:
        if 'sc-status' not in df.columns or 'time-taken' not in df.columns:
            raise ValueError("Required columns 'sc-status' or 'time-taken' not found in log data")
        
        summary = df.groupby('sc-status').agg(
            count=('sc-status', 'size'),
            avg_time_taken=('time-taken', 'mean'),
            max_time_taken=('time-taken', 'max'),
            min_time_taken=('time-taken', 'min')
        ).reset_index()
        
        summary.columns = ['sc_status', 'count', 'avg_time_taken', 'max_time_taken', 'min_time_taken']
        return summary
    except Exception as e:
        raise ValueError(f"Error generating summary: {str(e)}")

def create_pivot_table(df):
    if 'sc-status' in df.columns and 'cs-uri-stem' in df.columns:
        pivot = pd.pivot_table(
            df,
            values='time-taken',
            index='cs-uri-stem',
            columns='sc-status',
            aggfunc=['count', 'mean', 'max'],
            fill_value=0
        )
        pivot.columns = ['_'.join(map(str, col)) for col in pivot.columns]
        return pivot.reset_index()
    return None

def get_error_apps(df):
    if 'sc-status' in df.columns and 'cs-uri-stem' in df.columns:
        errors = df[df['sc-status'] >= 500]
        error_summary = errors.groupby('cs-uri-stem').agg(
            error_count=('sc-status', 'size'),
            avg_time=('time-taken', 'mean'),
            max_time=('time-taken', 'max')
        ).reset_index()
        return error_summary
    return None

def create_xlsx(summary_df, raw_df, pivot_df=None, error_df=None):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='StatusSummary', index=False)
            raw_df.to_excel(writer, sheet_name='RawData', index=False)
            if pivot_df is not None:
                pivot_df.to_excel(writer, sheet_name='PivotTable', index=False)
            if error_df is not None:
                error_df.to_excel(writer, sheet_name='ErrorSummary', index=False)
        output.seek(0)
        return output
    except Exception as e:
        raise ValueError(f"Error creating XLSX file: {str(e)}")

st.title("IIS Log Analyzer with Visualizations")

uploaded_file = st.file_uploader("Upload IIS .log file", type=["log"])

if uploaded_file:
    try:
        file_content = uploaded_file.read()
        raw_df = parse_iis_log(file_content)
        summary_df = generate_summary(raw_df)
        pivot_df = create_pivot_table(raw_df)
        error_df = get_error_apps(raw_df)
        
        xlsx_output = create_xlsx(summary_df, raw_df, pivot_df, error_df)
        
        st.success("File processed successfully!")
        
        st.download_button(
            label="Download XLSX (with Pivot and Error Summary)",
            data=xlsx_output,
            file_name="IIS_log_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Display Pivot Table
        st.subheader("Pivot Table: Requests by Endpoint and Status")
        if pivot_df is not None:
            st.dataframe(pivot_df)
        else:
            st.info("No pivot data available (missing required columns).")
        
        # Display Error Summary
        st.subheader("Which Apps/Services Had Errors (Status >= 500)")
        if error_df is not None and not error_df.empty:
            st.dataframe(error_df)
        else:
            st.info("No errors found in the logs.")
        
        # Charts and Timelines
        st.subheader("Visualizations")
        
        # Bar Chart: Status Code Counts
        if 'sc-status' in raw_df.columns:
            status_counts = raw_df['sc-status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            bar_chart = alt.Chart(status_counts).mark_bar().encode(
                x='Status:O',
                y='Count:Q',
                color='Status:O',
                tooltip=['Status', 'Count']
            ).properties(title="Status Code Distribution")
            st.altair_chart(bar_chart, use_container_width=True)
        
        # Timeline: Requests Over Time
        if 'datetime' in raw_df.columns:
            raw_df['hour'] = raw_df['datetime'].dt.floor('H')  # Group by hour for timeline
            timeline_data = raw_df.groupby('hour').size().reset_index(name='Request Count')
            line_chart = alt.Chart(timeline_data).mark_line().encode(
                x='hour:T',
                y='Request Count:Q',
                tooltip=['hour', 'Request Count']
            ).properties(title="Requests Timeline (Hourly)")
            st.altair_chart(line_chart, use_container_width=True)
        
        # Scatter Plot: Time Taken vs Time (for Errors)
        if 'datetime' in raw_df.columns and 'time-taken' in raw_df.columns:
            errors = raw_df[raw_df['sc-status'] >= 500]
            if not errors.empty:
                scatter = alt.Chart(errors).mark_circle().encode(
                    x='datetime:T',
                    y='time-taken:Q',
                    color='sc-status:O',
                    tooltip=['datetime', 'time-taken', 'cs-uri-stem', 'sc-status']
                ).properties(title="Error Response Times Timeline")
                st.altair_chart(scatter, use_container_width=True)
            else:
                st.info("No errors to plot.")
        
        # Preview Sections (as before)
        st.subheader("Preview of Status Summary")
        st.dataframe(summary_df)
        
        st.subheader("Preview of Raw Data (first 10 rows)")
        st.dataframe(raw_df.head(10))
        
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
