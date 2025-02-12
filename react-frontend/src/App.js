import React, { useState, useEffect } from "react";
import { io } from "socket.io-client";
import axios from "axios";
import jsPDF from "jspdf";
import styles from './App.module.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8080";
const socket = io(process.env.REACT_APP_WS_URL || BACKEND_URL, {
    transports: ['polling', 'websocket'],
    cors: {
        origin: "*",
        methods: ["GET", "POST"]
    }
});

function App() {
    const [view, setView] = useState("create");
    const [reportId, setReportId] = useState(null);
    const [reportNumber, setReportNumber] = useState("");
    const [reportStatement, setReportStatement] = useState("");
    const [reportAuthors, setReportAuthors] = useState("");
    const [questionNumber, setQuestionNumber] = useState("");
    const [questionStatement, setQuestionStatement] = useState("");
    const [questions, setQuestions] = useState([]);
    const [currentQuestion, setCurrentQuestion] = useState(null);
    const [subtopicTitle, setSubtopicTitle] = useState("");
    const [procedures, setProcedures] = useState("");
    const [explanation, setExplanation] = useState("");
    const [citations, setCitations] = useState("");
    const [image, setImage] = useState(null);
    const [figureDescription, setFigureDescription] = useState("");
    const [editingSubtopic, setEditingSubtopic] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [showPdfSettings, setShowPdfSettings] = useState(false);
    const [pdfOptions, setPdfOptions] = useState({
        includeImages: true,
        includeExplanations: true,
        includeCitations: true,
        pageSize: 'a4',
        orientation: 'portrait'
    });

    // Filter questions based on search term
    const filteredQuestions = questions.filter(q => 
        !searchTerm || 
        q.number.toLowerCase().includes(searchTerm.toLowerCase()) ||
        q.statement.toLowerCase().includes(searchTerm.toLowerCase()) ||
        q.subtopics.some(s => 
            s.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
            s.procedures.toLowerCase().includes(searchTerm.toLowerCase()) ||
            s.explanation.toLowerCase().includes(searchTerm.toLowerCase())
        )
    );

    // Socket.IO event listeners
    useEffect(() => {
        socket.on("connect", () => {
            console.log("Connected to server:", BACKEND_URL);
        });

        socket.on("connect_error", (error) => {
            console.error("Connection error:", error);
        });

        socket.on("error", (error) => {
            console.error("Socket error:", error);
        });

        socket.on("question_added", (question) => {
            console.log("Question added via socket:", question);
            // We'll handle question addition in the createQuestion function
        });

        socket.on("subtopic_added", (data) => {
            console.log("Subtopic added:", data);
            setQuestions(prevQuestions => {
                return prevQuestions.map(q => {
                    if (q.id === data.question_id) {
                        return {
                            ...q,
                            subtopics: [...q.subtopics, data.subtopic]
                        };
                    }
                    return q;
                });
            });
            
            // Update currentQuestion if this subtopic belongs to it
            setCurrentQuestion(prevQuestion => {
                if (prevQuestion && prevQuestion.id === data.question_id) {
                    return {
                        ...prevQuestion,
                        subtopics: [...prevQuestion.subtopics, data.subtopic]
                    };
                }
                return prevQuestion;
            });
        });

        socket.on("subtopic_updated", (data) => {
            console.log("Subtopic updated:", data);
            setQuestions(prevQuestions => {
                return prevQuestions.map(q => {
                    if (q.id === data.question_id) {
                        return {
                            ...q,
                            subtopics: q.subtopics.map(s => 
                                s.id === data.subtopic.id ? data.subtopic : s
                            )
                        };
                    }
                    return q;
                });
            });

            // Update currentQuestion if this subtopic belongs to it
            setCurrentQuestion(prevQuestion => {
                if (prevQuestion && prevQuestion.id === data.question_id) {
                    return {
                        ...prevQuestion,
                        subtopics: prevQuestion.subtopics.map(s =>
                            s.id === data.subtopic.id ? data.subtopic : s
                        )
                    };
                }
                return prevQuestion;
            });
        });

        // Cleanup function to remove event listeners
        return () => {
            socket.off("connect");
            socket.off("connect_error");
            socket.off("error");
            socket.off("question_added");
            socket.off("subtopic_added");
            socket.off("subtopic_updated");
        };
    }, []); // Empty dependency array means this runs once on mount

    // Function to join a room when a lab report is loaded
    const joinRoom = (reportId) => {
        if (reportId) {
            console.log("Joining room:", reportId);
            socket.emit('join', { room: reportId });
        }
    };

    useEffect(() => {
        // Get report ID from URL
        const params = new URLSearchParams(window.location.search);
        const id = params.get('reportId');
        if (id) {
            setReportId(id);
            loadLabReport(id);
            joinRoom(id); // Join the socket room
        }
    }, []);

    const loadLabReport = async (id) => {
        try {
            console.log("Loading lab report:", id);
            const response = await axios.get(`${BACKEND_URL}/api/lab-reports/${id}`);
            console.log("Lab report loaded:", response.data);
            setReportNumber(response.data.number);
            setReportStatement(response.data.statement);
            setReportAuthors(response.data.authors);
            setQuestions(response.data.questions || []);
            setView("home");
        } catch (error) {
            console.error('Error loading lab report:', error);
            setError('Failed to load lab report');
        }
    };

    const createLabReport = async () => {
        if (!reportNumber || !reportStatement || !reportAuthors) {
            return alert("Please enter lab number, statement, and authors!");
        }

        try {
            console.log("Creating lab report...");
            const response = await axios.post(`${BACKEND_URL}/api/lab-reports`, {
                number: reportNumber,
                statement: reportStatement,
                authors: reportAuthors
            });

            console.log("Lab report created:", response.data);
            const newReportId = response.data.id;
            setReportId(newReportId);
            
            // Update URL with report ID
            const newUrl = `${window.location.pathname}?reportId=${newReportId}`;
            window.history.pushState({ path: newUrl }, '', newUrl);

            // Join the socket room for this report
            socket.emit('join', { room: newReportId });
            
            setView("home");
        } catch (error) {
            console.error('Error creating lab report:', error.response?.data || error.message);
            alert('Failed to create lab report. Please try again.');
        }
    };

    const updateLabReport = async () => {
        if (!reportNumber || !reportStatement || !reportAuthors) {
            return alert("Please enter lab number, statement, and authors!");
        }

        try {
            setIsLoading(true);
            const response = await axios.put(`${BACKEND_URL}/api/lab-reports/${reportId}`, {
                number: reportNumber,
                statement: reportStatement,
                authors: reportAuthors
            });

            // Update the local state with the response data
            if (response.data) {
                setReportNumber(response.data.number);
                setReportStatement(response.data.statement);
                setReportAuthors(response.data.authors);
                if (response.data.questions) {
                    setQuestions(response.data.questions);
                }
            }

            alert('Lab details updated successfully!');
        } catch (error) {
            console.error('Error updating lab report:', error);
            alert('Failed to update lab report');
        } finally {
            setIsLoading(false);
        }
    };

    const createQuestion = async () => {
        if (!questionNumber || !questionStatement) {
            console.error("Missing required fields:", { questionNumber, questionStatement });
            return alert("Please enter both question number and statement!");
        }

        if (!reportId) {
            console.error("No reportId found");
            return alert("No active lab report! Please create a lab report first.");
        }

        try {
            setIsLoading(true);
            console.log("Creating question:", {
                url: `${BACKEND_URL}/api/lab-reports/${reportId}/questions`,
                data: {
                    number: questionNumber,
                    statement: questionStatement
                }
            });

            const response = await axios.post(`${BACKEND_URL}/api/lab-reports/${reportId}/questions`, {
                number: questionNumber,
                statement: questionStatement
            });

            console.log("Question created successfully:", response.data);

            // Add the new question to the list
            setQuestions(prevQuestions => [...prevQuestions, response.data]);
            
            // Clear the form
            setQuestionNumber("");
            setQuestionStatement("");

            // Set the current question and navigate to question view
            setCurrentQuestion(response.data);
            setView("question");
            
        } catch (error) {
            console.error('Error creating question:', {
                error: error,
                response: error.response?.data,
                status: error.response?.status,
                message: error.message,
                reportId: reportId,
                questionData: {
                    number: questionNumber,
                    statement: questionStatement
                }
            });
            alert('Failed to create question. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const createSubtopic = async () => {
        if (!subtopicTitle) {
            return alert("Please enter a subtopic title!");
        }

        try {
            setIsLoading(true);
            console.log("Creating subtopic:", {
                reportId,
                questionId: currentQuestion.id,
                data: {
                    title: subtopicTitle,
                    procedures,
                    explanation,
                    citations,
                    image_url: image,
                    figure_description: figureDescription
                }
            });

            const response = await axios.post(
                `${BACKEND_URL}/api/lab-reports/${reportId}/questions/${currentQuestion.id}/subtopics`,
                {
                    title: subtopicTitle,
                    procedures,
                    explanation,
                    citations,
                    image_url: image,
                    figure_description: figureDescription
                }
            );

            console.log("Subtopic created:", response.data);

            // Clear the form
            setSubtopicTitle("");
            setProcedures("");
            setExplanation("");
            setCitations("");
            setImage(null);
            setFigureDescription("");

        } catch (error) {
            console.error('Error creating subtopic:', error);
            alert('Failed to create subtopic. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const updateSubtopic = async () => {
        if (!editingSubtopic || !subtopicTitle) {
            return alert("Please enter a subtopic title!");
        }

        try {
            setIsLoading(true);
            console.log("Updating subtopic:", {
                reportId,
                questionId: currentQuestion.id,
                subtopicId: editingSubtopic,
                data: {
                    title: subtopicTitle,
                    procedures,
                    explanation,
                    citations,
                    image_url: image,
                    figure_description: figureDescription
                }
            });

            const response = await axios.put(
                `${BACKEND_URL}/api/lab-reports/${reportId}/questions/${currentQuestion.id}/subtopics/${editingSubtopic}`,
                {
                    title: subtopicTitle,
                    procedures,
                    explanation,
                    citations,
                    image_url: image,
                    figure_description: figureDescription
                }
            );

            console.log("Subtopic updated successfully:", response.data);

            // Clear the form
            setSubtopicTitle("");
            setProcedures("");
            setExplanation("");
            setCitations("");
            setImage(null);
            setFigureDescription("");
            setEditingSubtopic(null);

        } catch (error) {
            console.error('Error updating subtopic:', {
                error: error,
                response: error.response?.data,
                status: error.response?.status,
                message: error.message
            });
            alert('Failed to update subtopic. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyPress = (e) => {
            // Ctrl/Cmd + S to save/update
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                if (editingSubtopic) {
                    updateSubtopic();
                } else if (subtopicTitle) {
                    createSubtopic();
                }
            }
            // Esc to cancel edit
            if (e.key === 'Escape' && editingSubtopic) {
                e.preventDefault();
                setEditingSubtopic(null);
                // Clear form
                setSubtopicTitle("");
                setProcedures("");
                setExplanation("");
                setCitations("");
                setImage(null);
                setFigureDescription("");
            }
        };

        window.addEventListener('keydown', handleKeyPress);
        return () => window.removeEventListener('keydown', handleKeyPress);
    }, [editingSubtopic, subtopicTitle]);

    // Auto-save functionality
    useEffect(() => {
        // Save form state to localStorage every 30 seconds
        const saveInterval = setInterval(() => {
            if (subtopicTitle || procedures || explanation || citations || image || figureDescription) {
                localStorage.setItem('draftSubtopic', JSON.stringify({
                    title: subtopicTitle,
                    procedures,
                    explanation,
                    citations,
                    image_url: image,
                    figure_description: figureDescription,
                    timestamp: new Date().toISOString()
                }));
            }
        }, 30000);

        return () => clearInterval(saveInterval);
    }, [subtopicTitle, procedures, explanation, citations, image, figureDescription]);

    // Load draft on component mount
    useEffect(() => {
        const draft = localStorage.getItem('draftSubtopic');
        if (draft) {
            const draftData = JSON.parse(draft);
            const draftAge = new Date() - new Date(draftData.timestamp);
            const draftAgeHours = draftAge / (1000 * 60 * 60);
            
            // Only restore drafts less than 24 hours old
            if (draftAgeHours < 24 && window.confirm('Would you like to restore your unsaved work?')) {
                setSubtopicTitle(draftData.title || "");
                setProcedures(draftData.procedures || "");
                setExplanation(draftData.explanation || "");
                setCitations(draftData.citations || "");
                setImage(draftData.image_url || null);
                setFigureDescription(draftData.figure_description || "");
            } else {
                localStorage.removeItem('draftSubtopic');
            }
        }
    }, []);

    // PDF Settings Modal
    const PdfSettingsModal = () => (
        <div className={styles.modalOverlay} onClick={() => setShowPdfSettings(false)}>
            <div className={styles.modal} onClick={e => e.stopPropagation()}>
                <h3>PDF Export Settings</h3>
                <div className={styles.formGroup}>
                    <label className={styles.checkboxLabel}>
                        <input
                            type="checkbox"
                            checked={pdfOptions.includeImages}
                            onChange={e => setPdfOptions({...pdfOptions, includeImages: e.target.checked})}
                        />
                        Include Images
                    </label>
                </div>
                <div className={styles.formGroup}>
                    <label className={styles.checkboxLabel}>
                        <input
                            type="checkbox"
                            checked={pdfOptions.includeExplanations}
                            onChange={e => setPdfOptions({...pdfOptions, includeExplanations: e.target.checked})}
                        />
                        Include Explanations
                    </label>
                </div>
                <div className={styles.formGroup}>
                    <label className={styles.checkboxLabel}>
                        <input
                            type="checkbox"
                            checked={pdfOptions.includeCitations}
                            onChange={e => setPdfOptions({...pdfOptions, includeCitations: e.target.checked})}
                        />
                        Include Citations
                    </label>
                </div>
                <div className={styles.formGroup}>
                    <label>Page Size</label>
                    <select 
                        value={pdfOptions.pageSize}
                        onChange={e => setPdfOptions({...pdfOptions, pageSize: e.target.value})}
                    >
                        <option value="a4">A4</option>
                        <option value="letter">Letter</option>
                        <option value="legal">Legal</option>
                    </select>
                </div>
                <div className={styles.formGroup}>
                    <label>Orientation</label>
                    <select 
                        value={pdfOptions.orientation}
                        onChange={e => setPdfOptions({...pdfOptions, orientation: e.target.value})}
                    >
                        <option value="portrait">Portrait</option>
                        <option value="landscape">Landscape</option>
                    </select>
                </div>
                <button 
                    className={styles.primaryButton}
                    onClick={() => setShowPdfSettings(false)}
                >
                    Save Settings
                </button>
            </div>
        </div>
    );

    // Loading Overlay
    const LoadingOverlay = () => (
        isLoading && (
            <div className={styles.loadingOverlay}>
                <div className={styles.loadingSpinner}></div>
                <p>Processing...</p>
            </div>
        )
    );

    // Add loading overlay component
    const renderCreateView = () => (
        <div className={styles.container}>
            <header className={styles.header}>
                <h1 className={styles.title}>Create New Lab Report</h1>
            </header>

            <div className={styles.form}>
                <div className={styles.formGroup}>
                    <label className={styles.label}>Lab Number:</label>
                    <input
                        type="text"
                        className={styles.input}
                        value={reportNumber}
                        onChange={(e) => setReportNumber(e.target.value)}
                        placeholder="e.g., 1, 2, etc."
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Lab Statement:</label>
                    <textarea
                        className={styles.textarea}
                        value={reportStatement}
                        onChange={(e) => setReportStatement(e.target.value)}
                        placeholder="e.g., Access Control"
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Authors:</label>
                    <input
                        type="text"
                        className={styles.input}
                        value={reportAuthors}
                        onChange={(e) => setReportAuthors(e.target.value)}
                        placeholder="e.g., John Doe, Jane Smith"
                    />
                </div>

                <button 
                    className={styles.primaryButton}
                    onClick={createLabReport}
                >
                    Create Lab Report
                </button>
            </div>
        </div>
    );

    const renderHome = () => (
        <div className={styles.container}>
            <header className={styles.header}>
                <div>
                    <h1 className={styles.title}>Lab {reportNumber}: {reportStatement}</h1>
                    <p className={styles.subtitle}>Authors: {reportAuthors}</p>
                </div>
                <div className={styles.buttonGroup}>
                    <button 
                        className={styles.secondaryButton}
                        onClick={() => setView("edit")}
                    >
                        Edit Lab Details
                    </button>
                    <button 
                        className={styles.primaryButton}
                        onClick={async () => {
                            const doc = new jsPDF({
                                orientation: pdfOptions.orientation,
                                unit: "mm",
                                format: pdfOptions.pageSize,
                            });

                            doc.setFontSize(24);
                            doc.text(`Lab ${reportNumber}: ${reportStatement}`, 105, 80, { align: 'center' });
                            
                            doc.setFontSize(16);
                            doc.text(reportAuthors, 105, 100, { align: 'center' });
                            
                            // Add a new page for content
                            doc.addPage();
                            
                            // Reset position for content
                            let y = 20;
                            
                            for (const question of filteredQuestions) {
                                doc.setFontSize(20);
                                doc.setFont("times", "bold");
                                doc.text(`Question ${question.number}: ${question.statement}`, 20, y);
                                y += 12;

                                for (let index = 0; index < question.subtopics.length; index++) {
                                    const subtopic = question.subtopics[index];
                                    const subtopicLabel = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("")[index] || `(${index + 1})`; // A, B, C... fallback to numbers if needed

                                    doc.setFontSize(16);
                                    doc.setFont("times", "bolditalic");
                                    doc.text(`${subtopicLabel}. ${subtopic.title}`, 20, y, { underline: true });
                                    y += 10;

                                    // First show procedures
                                    doc.setFontSize(12);
                                    doc.setFont("times", "bold");
                                    doc.text("Procedures + Commands:", 20, y, { underline: true });
                                    y += 6;
                                    doc.setFont("times", "normal");
                                    doc.text(subtopic.procedures || "None", 20, y, { maxWidth: 160 });
                                    y += doc.splitTextToSize(subtopic.procedures || "", 160).length * 5;
                                    y += 8;

                                    // Then show image and figure description if they exist
                                    if (pdfOptions.includeImages && subtopic.image_url) {
                                        try {
                                            // Add the image
                                            doc.addImage(
                                                subtopic.image_url,
                                                'JPEG',  // or 'PNG' depending on the image type
                                                20,      // x position
                                                y,       // y position
                                                160,     // width (adjusted to fit page)
                                                80       // height (adjusted proportionally)
                                            );
                                            y += 85;  // Move down past the image

                                            // Add figure description if it exists
                                            if (subtopic.figure_description) {
                                                doc.setFont("times", "italic");
                                                doc.text(`Figure ${index + 1}: ${subtopic.figure_description}`, 20, y, { maxWidth: 160 });
                                                y += doc.splitTextToSize(subtopic.figure_description, 160).length * 5;
                                            }
                                        } catch (error) {
                                            console.error('Error adding image to PDF:', error);
                                            // Add error message in the PDF
                                            doc.setFont("times", "italic");
                                            doc.setTextColor(255, 0, 0);  // Red color for error
                                            doc.text("Error: Could not add image", 20, y);
                                            doc.setTextColor(0, 0, 0);    // Reset to black
                                            y += 5;
                                        }
                                        y += 8;
                                    }

                                    // Then show explanation if enabled
                                    if (pdfOptions.includeExplanations) {
                                        doc.setFontSize(12);
                                        doc.setFont("times", "bold");
                                        doc.text("Explanation of Output:", 20, y, { underline: true });
                                        y += 6;
                                        doc.setFont("times", "normal");
                                        doc.text(subtopic.explanation || "None", 20, y, { maxWidth: 160 });
                                        y += doc.splitTextToSize(subtopic.explanation || "", 160).length * 5;
                                        y += 8;
                                    }

                                    // Finally show citations if enabled
                                    if (pdfOptions.includeCitations) {
                                        doc.setFontSize(12);
                                        doc.setFont("times", "bold");
                                        doc.text("Citations:", 20, y, { underline: true });
                                        y += 6;
                                        doc.setFont("times", "normal");
                                        doc.text(subtopic.citations || "None", 20, y, { maxWidth: 160 });
                                        y += doc.splitTextToSize(subtopic.citations || "", 160).length * 5;
                                        y += 8;
                                    }

                                    // Add a new page if we're running out of space
                                    if (y > 270) {
                                        doc.addPage();
                                        y = 20;
                                    }
                                }
                                y += 10;
                                if (y > 270) {
                                    doc.addPage();
                                    y = 20;
                                }
                            }

                            doc.save("LabReport.pdf");
                        }}
                    >
                        Complete Lab Report
                    </button>
                    <button 
                        className={styles.secondaryButton}
                        onClick={() => setShowPdfSettings(true)}
                    >
                        PDF Settings
                    </button>
                    <button 
                        className={styles.dangerButton}
                        onClick={async () => {
                            if (window.confirm('Are you sure you want to reset all data? This action cannot be undone.')) {
                                try {
                                    await axios.delete(`${BACKEND_URL}/api/lab-reports/${reportId}`);
                                    
                                    // Clear all state
                                    setQuestions([]);
                                    setQuestionNumber("");
                                    setQuestionStatement("");
                                    setCurrentQuestion(null);
                                    setSubtopicTitle("");
                                    setProcedures("");
                                    setExplanation("");
                                    setCitations("");
                                    setImage(null);
                                    setFigureDescription("");
                                    setView("home");
                                    setEditingSubtopic(null);
                                    
                                    // Show success message
                                    alert('All data has been reset successfully');
                                } catch (error) {
                                    console.error('Error resetting data:', error);
                                    alert('Failed to reset data. Please try again.');
                                }
                            }
                        }}
                    >
                        Reset All Data
                    </button>
                </div>
            </header>

            <div className={styles.form}>
                <div className={styles.formGroup}>
                    <label className={styles.label}>Question Number:</label>
                    <input
                        type="text"
                        className={styles.input}
                        value={questionNumber}
                        onChange={(e) => setQuestionNumber(e.target.value)}
                        placeholder="e.g., 1.1, 2a, etc."
                    />
                </div>
                <div className={styles.formGroup}>
                    <label className={styles.label}>Question Statement:</label>
                    <textarea
                        className={styles.textarea}
                        value={questionStatement}
                        onChange={(e) => setQuestionStatement(e.target.value)}
                        placeholder="Enter the question statement..."
                    />
                </div>
                <button 
                    className={styles.primaryButton}
                    onClick={createQuestion}
                >
                    Add Question
                </button>
            </div>

            <div className={styles.questionList}>
                <h2>Created Questions:</h2>
                {filteredQuestions.map((q, index) => (
                    <div key={q.id} className={styles.questionCard}>
                        <div className={styles.questionHeader}>
                            <h3 className={styles.questionTitle}>
                                Question {q.number}: {q.statement}
                            </h3>
                            <div className={styles.buttonGroup}>
                                <button 
                                    className={styles.secondaryButton}
                                    onClick={() => {
                                        setCurrentQuestion(q);
                                        setQuestionNumber(q.number);
                                        setQuestionStatement(q.statement);
                                        setView("question");
                                    }}
                                >
                                    Edit Question
                                </button>
                            </div>
                        </div>
                        <div className={styles.subtopicList}>
                            <p>Subtopics ({q.subtopics.length}):</p>
                            {q.subtopics.map((s, sIndex) => (
                                <div key={s.id} className={styles.subtopicCard}>
                                    <h4 className={styles.subtopicTitle}>{s.title}</h4>
                                    {s.procedures && <p><strong>Procedures:</strong> {s.procedures}</p>}
                                    {s.explanation && <p><strong>Explanation:</strong> {s.explanation}</p>}
                                    {s.citations && <p><strong>Citations:</strong> {s.citations}</p>}
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            <div className={styles.searchBar}>
                <input 
                    type="text" 
                    value={searchTerm} 
                    onChange={(e) => setSearchTerm(e.target.value)} 
                    placeholder="Search questions..."
                />
            </div>
        </div>
    );

    const renderEditView = () => (
        <div className={styles.container}>
            <header className={styles.header}>
                <h1 className={styles.title}>Edit Lab Details</h1>
                <button 
                    className={styles.secondaryButton}
                    onClick={() => setView("home")}
                >
                    Back to Questions
                </button>
            </header>

            <div className={styles.form}>
                <div className={styles.formGroup}>
                    <label className={styles.label}>Lab Number:</label>
                    <input
                        type="text"
                        className={styles.input}
                        value={reportNumber}
                        onChange={(e) => setReportNumber(e.target.value)}
                        placeholder="e.g., 1, 2, etc."
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Lab Statement:</label>
                    <textarea
                        className={styles.textarea}
                        value={reportStatement}
                        onChange={(e) => setReportStatement(e.target.value)}
                        placeholder="e.g., Access Control"
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Authors:</label>
                    <input
                        type="text"
                        className={styles.input}
                        value={reportAuthors}
                        onChange={(e) => setReportAuthors(e.target.value)}
                        placeholder="e.g., John Doe, Jane Smith"
                    />
                </div>

                <button 
                    className={styles.primaryButton}
                    onClick={updateLabReport}
                >
                    Update Lab Details
                </button>
            </div>
        </div>
    );

    const renderQuestionView = () => (
        <div className={styles.container}>
            <header className={styles.header}>
                <h1 className={styles.title}>
                    Question {currentQuestion?.number}
                </h1>
                <div className={styles.buttonGroup}>
                    <button 
                        className={styles.secondaryButton}
                        onClick={() => {
                            setCurrentQuestion(null);
                            setView("home");
                        }}
                    >
                        Back to Questions
                    </button>
                </div>
            </header>

            <div className={styles.form}>
                <div className={styles.formGroup}>
                    <label className={styles.label}>Subtopic Title:</label>
                    <input
                        type="text"
                        className={styles.input}
                        value={subtopicTitle}
                        onChange={(e) => setSubtopicTitle(e.target.value)}
                        placeholder="Enter subtopic title..."
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Procedures + Commands:</label>
                    <textarea
                        className={styles.textarea}
                        value={procedures}
                        onChange={(e) => setProcedures(e.target.value)}
                        placeholder="Enter procedures and commands..."
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Explanation of Output:</label>
                    <textarea
                        className={styles.textarea}
                        value={explanation}
                        onChange={(e) => setExplanation(e.target.value)}
                        placeholder="Explain the output..."
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Citations:</label>
                    <textarea
                        className={styles.textarea}
                        value={citations}
                        onChange={(e) => setCitations(e.target.value)}
                        placeholder="Add any citations..."
                    />
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Image:</label>
                    <div 
                        className={styles.dropZone}
                        onPaste={(e) => {
                            e.preventDefault();
                            const items = e.clipboardData.items;
                            for (const item of items) {
                                if (item.type.indexOf("image") !== -1) {
                                    const blob = item.getAsFile();
                                    const reader = new FileReader();
                                    reader.onload = () => {
                                        console.log('Image pasted:', reader.result.substring(0, 100) + '...');
                                        setImage(reader.result);
                                    };
                                    reader.readAsDataURL(blob);
                                }
                            }
                        }}
                        onClick={() => document.getElementById('imageInput').click()}
                    >
                        <p>Click to upload or paste (Ctrl+V) an image</p>
                        <input
                            id="imageInput"
                            type="file"
                            accept="image/*"
                            onChange={(e) => {
                                const file = e.target.files[0];
                                if (file) {
                                    const reader = new FileReader();
                                    reader.onloadend = () => {
                                        console.log('Image loaded:', reader.result.substring(0, 100) + '...');
                                        setImage(reader.result);
                                    };
                                    reader.readAsDataURL(file);
                                }
                            }}
                            style={{ display: 'none' }}
                        />
                    </div>
                    {image && (
                        <div className={styles.imagePreviewContainer}>
                            <img 
                                src={image} 
                                alt="Preview" 
                                className={styles.imagePreview}
                            />
                            <button
                                className={styles.removeImageButton}
                                onClick={() => setImage(null)}
                            >
                                Remove Image
                            </button>
                        </div>
                    )}
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Figure Description:</label>
                    <textarea
                        className={styles.textarea}
                        value={figureDescription}
                        onChange={(e) => setFigureDescription(e.target.value)}
                        placeholder="Describe the figure..."
                    />
                </div>

                <button 
                    className={styles.primaryButton}
                    onClick={editingSubtopic ? updateSubtopic : createSubtopic}
                >
                    {editingSubtopic ? 'Update Subtopic' : 'Add Subtopic'}
                </button>
                {editingSubtopic && (
                    <button 
                        className={styles.secondaryButton}
                        onClick={() => {
                            setSubtopicTitle("");
                            setProcedures("");
                            setExplanation("");
                            setCitations("");
                            setImage(null);
                            setFigureDescription("");
                            setEditingSubtopic(null);
                        }}
                        style={{ marginLeft: '10px' }}
                    >
                        Cancel Edit
                    </button>
                )}
            </div>

            <div className={styles.subtopicList}>
                <h3>Current Subtopics:</h3>
                {currentQuestion?.subtopics.map((s, index) => (
                    <div key={s.id} className={styles.subtopicCard}>
                        <div className={styles.questionHeader}>
                            <h4 className={styles.subtopicTitle}>{s.title}</h4>
                            <button 
                                className={styles.secondaryButton}
                                onClick={() => {
                                    setEditingSubtopic(s.id);
                                    setSubtopicTitle(s.title);
                                    setProcedures(s.procedures || "");
                                    setExplanation(s.explanation || "");
                                    setCitations(s.citations || "");
                                    setImage(s.image_url || null);
                                    setFigureDescription(s.figure_description || "");
                                }}
                            >
                                Edit
                            </button>
                        </div>
                        {s.procedures && <p><strong>Procedures:</strong> {s.procedures}</p>}
                        {s.explanation && <p><strong>Explanation:</strong> {s.explanation}</p>}
                        {s.citations && <p><strong>Citations:</strong> {s.citations}</p>}
                    </div>
                ))}
            </div>

            <button 
                className={styles.primaryButton}
                onClick={async () => {
                    const doc = new jsPDF({
                        orientation: pdfOptions.orientation,
                        unit: "mm",
                        format: pdfOptions.pageSize,
                    });

                    doc.setFontSize(24);
                    doc.text(`Lab ${reportNumber}: ${reportStatement}`, 105, 80, { align: 'center' });
                    
                    doc.setFontSize(16);
                    doc.text(reportAuthors, 105, 100, { align: 'center' });
                    
                    // Add a new page for content
                    doc.addPage();
                    
                    // Reset position for content
                    let y = 20;
                    
                    for (const question of filteredQuestions) {
                        doc.setFontSize(20);
                        doc.setFont("times", "bold");
                        doc.text(`Question ${question.number}: ${question.statement}`, 20, y);
                        y += 12;

                        for (let index = 0; index < question.subtopics.length; index++) {
                            const subtopic = question.subtopics[index];
                            const subtopicLabel = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("")[index] || `(${index + 1})`; // A, B, C... fallback to numbers if needed

                            doc.setFontSize(16);
                            doc.setFont("times", "bolditalic");
                            doc.text(`${subtopicLabel}. ${subtopic.title}`, 20, y, { underline: true });
                            y += 10;

                            // First show procedures
                            doc.setFontSize(12);
                            doc.setFont("times", "bold");
                            doc.text("Procedures + Commands:", 20, y, { underline: true });
                            y += 6;
                            doc.setFont("times", "normal");
                            doc.text(subtopic.procedures || "None", 20, y, { maxWidth: 160 });
                            y += doc.splitTextToSize(subtopic.procedures || "", 160).length * 5;
                            y += 8;

                            // Then show image and figure description if they exist
                            if (pdfOptions.includeImages && subtopic.image_url) {
                                try {
                                    // Add the image
                                    doc.addImage(
                                        subtopic.image_url,
                                        'JPEG',  // or 'PNG' depending on the image type
                                        20,      // x position
                                        y,       // y position
                                        160,     // width (adjusted to fit page)
                                        80       // height (adjusted proportionally)
                                    );
                                    y += 85;  // Move down past the image

                                    // Add figure description if it exists
                                    if (subtopic.figure_description) {
                                        doc.setFont("times", "italic");
                                        doc.text(`Figure ${index + 1}: ${subtopic.figure_description}`, 20, y, { maxWidth: 160 });
                                        y += doc.splitTextToSize(subtopic.figure_description, 160).length * 5;
                                    }
                                } catch (error) {
                                    console.error('Error adding image to PDF:', error);
                                    // Add error message in the PDF
                                    doc.setFont("times", "italic");
                                    doc.setTextColor(255, 0, 0);  // Red color for error
                                    doc.text("Error: Could not add image", 20, y);
                                    doc.setTextColor(0, 0, 0);    // Reset to black
                                    y += 5;
                                }
                                y += 8;
                            }

                            // Then show explanation if enabled
                            if (pdfOptions.includeExplanations) {
                                doc.setFontSize(12);
                                doc.setFont("times", "bold");
                                doc.text("Explanation of Output:", 20, y, { underline: true });
                                y += 6;
                                doc.setFont("times", "normal");
                                doc.text(subtopic.explanation || "None", 20, y, { maxWidth: 160 });
                                y += doc.splitTextToSize(subtopic.explanation || "", 160).length * 5;
                                y += 8;
                            }

                            // Finally show citations if enabled
                            if (pdfOptions.includeCitations) {
                                doc.setFontSize(12);
                                doc.setFont("times", "bold");
                                doc.text("Citations:", 20, y, { underline: true });
                                y += 6;
                                doc.setFont("times", "normal");
                                doc.text(subtopic.citations || "None", 20, y, { maxWidth: 160 });
                                y += doc.splitTextToSize(subtopic.citations || "", 160).length * 5;
                                y += 8;
                            }

                            // Add a new page if we're running out of space
                            if (y > 270) {
                                doc.addPage();
                                y = 20;
                            }
                        }
                        y += 10;
                        if (y > 270) {
                            doc.addPage();
                            y = 20;
                        }
                    }

                    doc.save("LabReport.pdf");
                }}
            >
                Complete Lab Report
            </button>
        </div>
    );

    if (isLoading) {
        return (
            <div className={styles.container}>
                <LoadingOverlay />
            </div>
        );
    }

    if (error) {
        return <div className={styles.container}>Error: {error}</div>;
    }

    if (showPdfSettings) {
        return (
            <div className={styles.container}>
                <PdfSettingsModal />
            </div>
        );
    }

    switch (view) {
        case "create":
            return renderCreateView();
        case "edit":
            return renderEditView();
        case "home":
            return renderHome();
        case "question":
            return renderQuestionView();
        default:
            return renderCreateView();
    }
};

export default App;
