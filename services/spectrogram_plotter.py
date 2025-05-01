# Filename: services/spectrogram_plotter.py
# Updated with refined theme application for better readability

import logging
import os
from typing import Any, Optional

# --- Matplotlib and Librosa Imports ---
try:
    import matplotlib

    matplotlib.use("Qt5Agg")  # Ensure Qt5 backend is used
    import matplotlib.pyplot as plt
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    # No FigureCanvas or Toolbar needed here
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    # Dummy types for hinting
    Axes = object  # type: ignore
    Figure = object  # type: ignore

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    NUMPY_AVAILABLE = False

try:
    if NUMPY_AVAILABLE:
        import librosa
        import librosa.display

        LIBROSA_AVAILABLE = True
    else:
        librosa = None  # type: ignore[assignment]
        LIBROSA_AVAILABLE = False
except ImportError:
    librosa = None  # type: ignore[assignment]
    LIBROSA_AVAILABLE = False

# --- Application Imports ---
try:
    from services.spectrogram_service import SpectrogramService

    SERVICE_AVAILABLE = True
except ImportError:
    SpectrogramService = None  # type: ignore[assignment]
    SERVICE_AVAILABLE = False

logger = logging.getLogger(__name__)


class SpectrogramPlotter:
    """
    Provides static methods for plotting spectrograms onto Matplotlib Axes.
    Uses SpectrogramService to fetch data. Includes basic theming.
    """

    @staticmethod
    def _get_text_color(theme: str) -> str:
        """Helper to get appropriate text color based on theme."""
        # Use brighter color for dark mode text
        return "#E0E0E0" if theme == "dark" else "#111111"

    @staticmethod
    def _apply_theme_to_axes(
        ax: Axes, figure: Figure, theme: str, colorbar: Optional[Any] = None  # type: ignore
    ):
        """Applies theme colors to the plot elements for better readability."""
        if not ax or not figure:
            return

        text_color = SpectrogramPlotter._get_text_color(theme)
        # Use slightly less intense background for dark mode axes for contrast
        axes_face_color = "#33373E" if theme == "dark" else "#F0F0F0"
        grid_color = "#55595F" if theme == "dark" else "#CCCCCC"  # For spines/borders

        try:
            # Set axes background
            ax.set_facecolor(axes_face_color)

            # Set color for axes borders (spines)
            for spine in ax.spines.values():
                spine.set_edgecolor(grid_color)  # type: ignore[attr-defined]

            # Set color for ticks and tick labels
            ax.tick_params(axis="x", colors=text_color, labelcolor=text_color)
            ax.tick_params(axis="y", colors=text_color, labelcolor=text_color)

            # Set color for Axis labels (X and Y)
            ax.xaxis.label.set_color(text_color)
            ax.yaxis.label.set_color(text_color)

            # Set color for Title
            if ax.title:  # Check if title exists
                ax.title.set_color(text_color)

            # Set color for Colorbar ticks and label
            if colorbar:
                colorbar.ax.yaxis.set_tick_params(
                    color=text_color, labelcolor=text_color
                )
                # Set colorbar tick labels explicitly
                plt.setp(plt.getp(colorbar.ax.axes, "yticklabels"), color=text_color)
                # Set colorbar axis label color if it exists
                if hasattr(colorbar.ax.yaxis.label, "set_color"):
                    colorbar.ax.yaxis.label.set_color(text_color)
                # Set colorbar outline/border color
                colorbar.outline.set_edgecolor(grid_color)

        except Exception as theme_err:
            logger.error(f"Error applying theme to axes: {theme_err}", exc_info=False)

    @staticmethod
    def plot(file_path: str, ax: Axes, figure: Figure, theme: str = "light") -> bool:  # type: ignore
        """
        Generates and displays the spectrogram for the given audio file path
        onto the provided Matplotlib Axes.

        Args:
            file_path: The absolute path to the audio file.
            ax: The Matplotlib Axes object to plot onto.
            figure: The Matplotlib Figure containing the axes (needed for colorbar).
            theme: The theme ('light' or 'dark') for styling.

        Returns:
            True if plotting was successful, False otherwise.
        """
        theme = theme.lower()
        text_color = SpectrogramPlotter._get_text_color(theme)
        # Get the figure's background color based on theme for consistency
        figure_bg_color = "#282c34" if theme == "dark" else "#FFFFFF"
        figure.patch.set_facecolor(figure_bg_color)  # Apply to figure background

        # --- Dependency Checks ---
        if not all(
            [
                MATPLOTLIB_AVAILABLE,
                NUMPY_AVAILABLE,
                LIBROSA_AVAILABLE,
                SERVICE_AVAILABLE,
            ]
        ):
            msg = "Missing dependencies for plotting spectrogram."
            logger.error(msg)
            ax.cla()
            ax.text(
                0.5, 0.5, msg, ha="center", va="center", wrap=True, color=text_color
            )
            SpectrogramPlotter._apply_theme_to_axes(
                ax, figure, theme
            )  # Style error message
            return False

        if not SERVICE_AVAILABLE:
            msg = "SpectrogramService not available."
            logger.error(msg)
            ax.cla()
            ax.text(
                0.5, 0.5, msg, ha="center", va="center", wrap=True, color=text_color
            )
            SpectrogramPlotter._apply_theme_to_axes(ax, figure, theme)
            return False

        # --- Clear previous plot ---
        ax.cla()

        # --- Get Spectrogram Data ---
        try:
            service = SpectrogramService()
            # Using load_duration=None to attempt loading full file (service might have internal limit)
            spec_data = service.get_spectrogram_data(file_path, load_duration=None)
        except Exception as e:
            logger.error(f"Error getting spectrogram data: {e}", exc_info=True)
            ax.text(
                0.5,
                0.5,
                f"Error getting spectrogram data:\n{e}",
                ha="center",
                va="center",
                wrap=True,
                color=text_color,
            )
            ax.set_title(
                f"Spectrogram Error", color=text_color
            )  # Set title color here too
            SpectrogramPlotter._apply_theme_to_axes(ax, figure, theme)
            return False

        # --- Handle errors from service ---
        basename = os.path.basename(file_path)
        if (
            spec_data.get("error")
            or "magnitude" not in spec_data
            or spec_data["magnitude"] is None
            or "sr" not in spec_data
            or spec_data["sr"] is None
        ):
            error_msg = spec_data.get(
                "error", "Missing spectrogram data (magnitude/sr)."
            )
            logger.warning(f"Cannot plot spectrogram for {basename}: {error_msg}")
            ax.text(
                0.5,
                0.5,
                f"Could not generate spectrogram:\n{error_msg}",
                ha="center",
                va="center",
                wrap=True,
                color=text_color,
            )
            ax.set_title(f"Spectrogram: {basename} (Error)", color=text_color)
            SpectrogramPlotter._apply_theme_to_axes(ax, figure, theme)
            return False

        # --- Plot Spectrogram ---
        cbar = None  # Initialize colorbar reference
        try:
            S_magnitude = spec_data["magnitude"]
            sr = spec_data["sr"]
            hop_length = spec_data.get("hop_length", 512)  # Use default if not in data

            # Convert amplitude spectrogram to dB scale
            S_db = librosa.amplitude_to_db(S_magnitude, ref=np.max)

            # Choose a colormap - 'magma' or 'viridis' often work well on dark/light
            cmap = "magma"

            # Display the spectrogram on the provided axes
            img = librosa.display.specshow(
                S_db,
                sr=sr,
                hop_length=hop_length,
                ax=ax,
                x_axis="time",
                y_axis="log",  # Logarithmic frequency scale
                cmap=cmap,
            )

            # Add color bar to the figure associated with the axes
            cbar = figure.colorbar(img, ax=ax, format="%+2.0f dB")

            # Set labels and title
            ax.set_title(f"Spectrogram: {basename}")  # Color set by theme method
            ax.set_ylabel("Frequency (Hz)")  # Color set by theme method
            ax.set_xlabel("Time (s)")  # Color set by theme method

            # Apply theme colors AFTER plotting elements exist
            SpectrogramPlotter._apply_theme_to_axes(ax, figure, theme, cbar)

            logger.info(f"Spectrogram plotted for: {basename}")
            return True  # Success

        except Exception as plot_err:
            logger.error(
                f"Error plotting spectrogram for {file_path}: {plot_err}", exc_info=True
            )
            # Display error on the plot itself
            ax.cla()  # Clear potentially partial plot
            ax.text(
                0.5,
                0.5,
                f"Error during plotting:\n{plot_err}",
                ha="center",
                va="center",
                wrap=True,
                color=text_color,
            )
            ax.set_title(f"Spectrogram: {basename} (Plotting Error)", color=text_color)
            SpectrogramPlotter._apply_theme_to_axes(
                ax, figure, theme, cbar
            )  # Apply theme to error text too
            return False
